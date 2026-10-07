// Diagnostic-only entry point. Links existing m5-trace libraries without editing them.
#include "arg.h"
#include "common.h"
#include "ggml-backend.h"
#include "llama.h"
#include "log.h"
#include "server-stream.h"

#include <clocale>
#include <csignal>
#include <cstring>
#include <cstdlib>
#include <mutex>
#include <set>
#include <stdexcept>
#include <nlohmann/json.hpp>

int llama_server(common_params & params, int argc, char ** argv);

namespace {
using json = nlohmann::json;
void require(bool value, const char * reason) { if (!value) throw std::runtime_error(reason); }

int route_layer(const char * name) {
    constexpr const char * prefix = "ffn_moe_topk-";
    if (std::strncmp(name, prefix, std::strlen(prefix))) return -1;
    const char * suffix = name + std::strlen(prefix);
    char * end = nullptr;
    long layer = std::strtol(suffix, &end, 10);
    require(end != suffix && *end == '\0' && layer >= 0 && layer <= 48, "Unexpected expert layer name");
    return int(layer);
}

json extract_ids(const ggml_tensor * t, const std::vector<uint8_t> & raw) {
    require(t->type == GGML_TYPE_I32 && t->ne[0] == 10 && t->ne[1] >= 1 && t->ne[1] <= 6 &&
            t->ne[2] == 1 && t->ne[3] == 1 && t->nb[0] == sizeof(int32_t) && t->nb[1] == 512*sizeof(int32_t),
            "Unexpected expert routing geometry or stride");
    json rows = json::array();
    for (int r = 0; r < t->ne[1]; ++r) {
        std::vector<int32_t> ids;
        for (int e = 0; e < 10; ++e) {
            const size_t offset = r*t->nb[1] + e*t->nb[0];
            require(offset + sizeof(int32_t) <= raw.size(), "Expert ID exceeds routing buffer");
            int32_t id;
            std::memcpy(&id, raw.data()+offset, sizeof(id));
            require(id >= 0 && id < 512, "Expert ID out of range");
            ids.push_back(id);
        }
        require(std::set<int32_t>(ids.begin(), ids.end()).size() == 10, "Duplicate experts within a token");
        rows.push_back(ids);
    }
    return rows;
}

void emit(const char * marker, const json & data) {
    std::fprintf(stderr, "%s %s\n", marker, data.dump().c_str());
}

struct state {
    std::string mode;
    uint64_t serial = 0;
    int64_t start = 0;
    ggml_tensor * pending = nullptr;
    bool failed = false;
    std::mutex mutex;
};

bool eval(ggml_tensor * t, bool ask, void * userdata) {
    auto & s = *static_cast<state *>(userdata);
    std::lock_guard<std::mutex> lock(s.mutex);
    try {
        const int layer = route_layer(t->name);
        const bool route = layer >= 0 && t->ne[1] >= 1 && t->ne[1] <= 6;
        const bool metadata = t->op == GGML_OP_NONE || t->op == GGML_OP_VIEW || t->op == GGML_OP_RESHAPE ||
                              t->op == GGML_OP_PERMUTE || t->op == GGML_OP_TRANSPOSE;
        const bool wanted = route || (s.mode == "split" && !metadata && ggml_nelements(t) > 0);
        if (ask) {
            if (!wanted || s.failed) return false;
            require(!s.pending && s.serial < 300000, "Overlapping callback or diagnostic event limit reached");
            s.pending = t; s.start = ggml_time_us(); ++s.serial;
            auto dims = [](const ggml_tensor * p) { return std::vector<int64_t>(p->ne, p->ne+4); };
            json data = {{"serial", s.serial}, {"cpu_us", s.start}, {"name", t->name},
                {"op", ggml_op_name(t->op)}, {"dst", dims(t)}, {"type", ggml_type_name(t->type)}};
            if (t->src[0]) { data["src0"] = dims(t->src[0]); data["src0_type"] = ggml_type_name(t->src[0]->type); }
            emit("M5_EVAL_BEGIN", data);
            return true;
        }
        require(wanted && s.pending == t, "Callback completion does not match its start");
        // The scheduler synchronizes before calling ask=false. IDs are read, never written.
        if (route) {
            std::vector<uint8_t> bytes(ggml_nbytes(t));
            ggml_backend_tensor_get(t, bytes.data(), 0, bytes.size());
            emit("M5_ROUTE", {{"serial", s.serial}, {"cpu_us", ggml_time_us()}, {"layer", layer},
                {"role", layer == 48 ? "helper" : "target"}, {"rows", t->ne[1]},
                {"row_stride_bytes", t->nb[1]}, {"ids", extract_ids(t, bytes)}});
        }
        emit("M5_EVAL_END", {{"serial", s.serial}, {"cpu_us", ggml_time_us()}});
        s.pending = nullptr;
        return true;
    } catch (const std::exception & error) {
        s.failed = true; emit("M5_EVAL_ERROR", {{"message", error.what()}}); return false;
    }
}

void self_test() {
    require(route_layer("ffn_moe_topk-0") == 0 && route_layer("ffn_moe_topk-48") == 48 &&
            route_layer("ffn_moe_argsort-0") == -1, "Layer matcher failed");
    ggml_tensor tensor{};
    tensor.type = GGML_TYPE_I32;
    tensor.ne[0] = 10; tensor.ne[1] = 5; tensor.ne[2] = tensor.ne[3] = 1;
    tensor.nb[0] = 4; tensor.nb[1] = 2048;
    std::vector<uint8_t> raw(5*2048, 0xff);
    for (int row = 0; row < 5; ++row) for (int e = 0; e < 10; ++e) {
        int32_t id = row*90+e;
        std::memcpy(raw.data()+row*2048+e*4, &id, 4);
    }
    auto result = extract_ids(&tensor, raw);
    require(result[4][9] == 369 && result[1][0] == 90, "Strided IDs were misread");
    int rejected = 0;
    auto expect_failure = [&](auto f) { try { f(); } catch (const std::exception &) { ++rejected; } };
    expect_failure([&] { route_layer("ffn_moe_topk-49"); });
    expect_failure([&] { route_layer("ffn_moe_topk-no"); });
    expect_failure([&] { extract_ids(&tensor, std::vector<uint8_t>(10)); });
    tensor.nb[1] = 40; expect_failure([&] { extract_ids(&tensor, raw); }); tensor.nb[1] = 2048;
    int32_t bad = 512; std::memcpy(raw.data(), &bad, 4);
    expect_failure([&] { extract_ids(&tensor, raw); });
    bad = 1; std::memcpy(raw.data(), &bad, 4);
    expect_failure([&] { extract_ids(&tensor, raw); });
    require(rejected == 6, "Invalid routing input was accepted");
    std::puts("M5 eval self-test passed: padded stride, layer roles, six invalid inputs; no backend initialized");
}
} // namespace

int main(int argc, char ** argv) {
    if (argc == 2 && std::strcmp(argv[1], "--self-test") == 0) { self_test(); return 0; }
    state data;
    const char * mode = std::getenv("GGML_M5_LAB_EVAL_MODE");
    data.mode = mode ? mode : "control";
    require(data.mode == "control" || data.mode == "routes" || data.mode == "split", "Unknown diagnostic mode");
    std::setlocale(LC_NUMERIC, "C");
    std::signal(SIGPIPE, SIG_IGN);
    common_init();
    server_stream_session_manager_start();
    common_params params;
    if (!common_params_parse(argc, argv, params, LLAMA_EXAMPLE_SERVER)) return 1;
    if (data.mode != "control") { params.cb_eval = eval; params.cb_eval_user_data = &data; }
    emit("M5_EVAL_CONFIG", {{"mode", data.mode}, {"synchronizes_graph_segments", data.mode != "control"},
        {"timings_excluded_from_speed_results", true}, {"route_rows_max", 6}, {"main_layers", 48}});
    llama_backend_init();
    llama_numa_init(params.numa);
    const int result = llama_server(params, argc, argv);
    common_log_flush(common_log_main());
    return data.failed ? 1 : result;
}
