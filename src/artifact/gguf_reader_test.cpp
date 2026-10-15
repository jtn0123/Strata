// src/artifact/gguf_reader_test.cpp - the reader refuses what it cannot arbitrate (synthetic GGUF, no model,
// no GPU).
//
//   1. two tensors with distinct names: the file opens and find() sees both;
//   2. the same name twice: refused at open, and the error names the tensor and the file - GGUF has no
//      index to say which of the two a name means, and find() is first-match, so the alternative is a
//      lookup that silently picks by position.
//   3. crafted headers: a string length that would wrap the bounds check, a tensor count no file of this
//      size can hold, an alignment that is not a power of two or would wrap the data start, a shape whose
//      element count wraps (to the count a caller expects), and a tensor past the end of the file;
//   4. damaged copies of a valid file - cut at every length, and every header byte set to a few values -
//      each opens or is refused, and every tensor in_bounds() passes is read through (built with
//      -fsanitize=address,undefined that shows no read outside the mapping).
//
// The fixtures are minimal GGUF v3 files written here, so the test needs neither gguf-py nor a shard.  A
// file is closed before it is removed: on Windows an open mapping keeps it.
#include "strata/artifact/gguf_reader.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace {
int g_fail = 0;
void check(bool ok, const char* what) {
    std::printf("  %-66s %s\n", what, ok ? "ok" : "FAIL");
    if (!ok) ++g_fail;
}

template <class T> void put(std::vector<uint8_t>& b, T v) {
    const auto n = b.size();
    b.resize(n + sizeof(T));
    std::memcpy(b.data() + n, &v, sizeof(T));
}
void put_str(std::vector<uint8_t>& b, const std::string& s) {
    put<uint64_t>(b, s.size());
    b.insert(b.end(), s.begin(), s.end());
}

// A GGUF v3 file of F32[8] tensors named `names`, laid out 32 bytes apart from a 32-byte-aligned data start.
std::filesystem::path write_gguf(const std::vector<std::string>& names) {
    std::vector<uint8_t> b;
    put<uint32_t>(b, 0x46554747u);   // "GGUF"
    put<uint32_t>(b, 3);
    put<uint64_t>(b, names.size());  // n_tensors
    put<uint64_t>(b, 0);             // n_kv
    for (size_t i = 0; i < names.size(); ++i) {
        put_str(b, names[i]);
        put<uint32_t>(b, 1);         // n_dims
        put<uint64_t>(b, 8);
        put<uint32_t>(b, 0);         // F32
        put<uint64_t>(b, 32 * i);    // offset from data_start
    }
    b.resize((b.size() + 31) / 32 * 32 + 32 * names.size(), 0);
    const auto path = std::filesystem::temp_directory_path() / "strata_gguf_reader_test.gguf";
    std::ofstream(path, std::ios::binary).write(reinterpret_cast<const char*>(b.data()), (std::streamsize)b.size());
    return path;
}

std::filesystem::path write_bytes(const std::vector<uint8_t>& b) {
    const auto path = std::filesystem::temp_directory_path() / "strata_gguf_reader_crafted.gguf";
    std::ofstream(path, std::ios::binary).write(reinterpret_cast<const char*>(b.data()), (std::streamsize) b.size());
    return path;
}

volatile uint64_t g_sink = 0;

// Opens `b` as a file and reads every tensor in_bounds() passes: "" when it opens, else the error.
std::string try_open(const std::vector<uint8_t>& b) {
    const auto path = write_bytes(b);
    std::string err;
    try {
        strata::GgufFile g(path.string());
        if (g.data_start() > g.file_size() || (g.alignment() & (g.alignment() - 1)) != 0) err = "bad layout";
        for (const auto& t : g.tensors()) {
            g_sink = g_sink + t.elements();
            if (!g.in_bounds(t)) continue;
            const uint8_t* p = g.tensor_data(t);
            for (uint64_t i = 0, n = strata::tensor_payload_bytes(t); i < n; ++i) g_sink = g_sink + p[i];
        }
    } catch (const std::exception& e) { err = *e.what() ? e.what() : "?"; }
    std::filesystem::remove(path);
    return err;
}

// The header up to the tensor directory: `n_tensors` and `n_kv` as given.
std::vector<uint8_t> header(uint64_t n_tensors, uint64_t n_kv) {
    std::vector<uint8_t> b;
    put<uint32_t>(b, 0x46554747u);
    put<uint32_t>(b, 3);
    put<uint64_t>(b, n_tensors);
    put<uint64_t>(b, n_kv);
    return b;
}

void put_tensor(std::vector<uint8_t>& b, const std::string& name, uint64_t n, uint32_t type, uint64_t offset) {
    put_str(b, name);
    put<uint32_t>(b, 1);
    put<uint64_t>(b, n);
    put<uint32_t>(b, type);
    put<uint64_t>(b, offset);
}

// One general.alignment key of GGUF type `type` (4 u32, 10 u64) and one F32[8] tensor, padded to 512 bytes.
std::vector<uint8_t> with_alignment(uint32_t type, uint64_t align) {
    std::vector<uint8_t> b = header(1, 1);
    put_str(b, "general.alignment");
    put<uint32_t>(b, type);
    if (type == 4)
        put<uint32_t>(b, (uint32_t) align);
    else
        put<uint64_t>(b, align);
    put_tensor(b, "a", 8, 0, 0);
    b.resize(512, 0);
    return b;
}

// A valid file with every kind of header field the damage below can hit: a string, a u32 alignment, arrays
// of u32 and of strings, and two F32[8] tensors.
std::vector<uint8_t> sample() {
    std::vector<uint8_t> b = header(2, 4);
    put_str(b, "general.architecture");
    put<uint32_t>(b, 8);
    put_str(b, "qwen4exp");
    put_str(b, "general.alignment");
    put<uint32_t>(b, 4);
    put<uint32_t>(b, 32);
    put_str(b, "x.u32s");
    put<uint32_t>(b, 9);
    put<uint32_t>(b, 4);
    put<uint64_t>(b, 3);
    for (uint32_t v : {1u, 2u, 3u}) put<uint32_t>(b, v);
    put_str(b, "x.strs");
    put<uint32_t>(b, 9);
    put<uint32_t>(b, 8);
    put<uint64_t>(b, 2);
    put_str(b, "x");
    put_str(b, "yz");
    put_tensor(b, "a", 8, 0, 0);
    put_tensor(b, "b", 8, 0, 32);
    b.resize((b.size() + 31) / 32 * 32 + 64, 0x5a);
    return b;
}
}  // namespace

int main() {
    std::printf("gguf_reader_test\n");
    {
        const auto path = write_gguf({"blk.0.attn_q.weight", "blk.0.attn_k.weight"});
        std::string err;
        size_t n = 0;
        bool both = false;
        try {
            strata::GgufFile g(path.string());
            n = g.tensors().size();
            both = g.find("blk.0.attn_q.weight") && g.find("blk.0.attn_k.weight");
        } catch (const std::exception& e) {
            err = e.what();
        }
        std::filesystem::remove(path);
        check(err.empty() && n == 2 && both, "distinct names: the file opens and find() sees both tensors");
    }
    {
        const auto path = write_gguf({"blk.0.attn_q.weight", "blk.0.attn_q.weight"});
        std::string err;
        try {
            strata::GgufFile g(path.string());
        } catch (const std::exception& e) {
            err = e.what();
        }
        std::filesystem::remove(path);
        check(!err.empty(), "the same name twice: refused at open");
        check(err.find("blk.0.attn_q.weight") != std::string::npos, "  the error names the tensor");
        check(err.find(path.filename().string()) != std::string::npos, "  the error names the file");
        if (!err.empty()) std::printf("  (%s)\n", err.c_str());
    }
    {
        std::vector<uint8_t> b = header(0, 1);
        put<uint64_t>(b, ~0ull - 15);   // a key length that wraps pos + n back below the file size
        b.resize(256, 0);
        const std::string err = try_open(b);
        check(err.find("unexpected end of file") != std::string::npos, "a string length that wraps: refused");
    }
    {
        std::vector<uint8_t> b = header(1ull << 26, 0);   // 64 Mi entries: gigabytes reserved before
        b.resize(4096, 0);
        const std::string err = try_open(b);
        check(err.find("cannot fit") != std::string::npos, "a tensor count the file cannot hold: refused");
    }
    {
        check(try_open(with_alignment(4, 32)).empty(), "general.alignment 32 (u32): opens");
        check(try_open(with_alignment(4, 64)).empty(), "general.alignment 64 (u32): opens");
        const std::string odd = try_open(with_alignment(4, 48));
        check(odd.find("power of two") != std::string::npos, "general.alignment 48: refused");
        const std::string wrap = try_open(with_alignment(10, ~0ull));
        check(wrap.find("power of two") != std::string::npos, "general.alignment 2^64-1 (u64, wraps): refused");
        const std::string big = try_open(with_alignment(10, 1ull << 63));
        check(big.find("power of two") != std::string::npos, "general.alignment 2^63: refused");
    }
    {
        strata::TensorInfo t;
        t.type = 0;
        t.shape = {2560, 1 + (1ull << 55)};   // 2560 * (1 + 2^55) wraps to 2560
        check(t.elements() == 0 && strata::tensor_payload_bytes(t) == 0,
              "a shape whose element count wraps: 0 elements, no byte count");
        t.shape = {2560, 2};
        check(t.elements() == 5120, "  a plain shape: its count");
    }
    {
        std::vector<uint8_t> b = header(3, 0);
        put_tensor(b, "inside", 8, 0, 0);
        put_tensor(b, "past.end", 8, 0, 1ull << 40);
        put_tensor(b, "unknown.type", 8, 99, 32);
        b.resize((b.size() + 31) / 32 * 32 + 64, 0);
        const auto path = write_bytes(b);
        bool inside = false, past = true, unknown = true;
        try {
            strata::GgufFile g(path.string());
            inside = g.in_bounds(*g.find("inside"));
            past = g.in_bounds(*g.find("past.end"));
            unknown = g.in_bounds(*g.find("unknown.type"));
        } catch (const std::exception&) {}
        std::filesystem::remove(path);
        check(inside && !past && !unknown, "in_bounds: a tensor inside, not one past the end or of no known size");
    }
    {
        const std::vector<uint8_t> good = sample();
        check(try_open(good).empty(), "the damage fixture opens undamaged");
        int opened = 0, refused = 0, bad = 0;
        auto tally = [&](const std::vector<uint8_t>& b) {
            const std::string err = try_open(b);
            err.empty() ? ++opened : ++refused;
            if (err == "bad layout") ++bad;
        };
        for (size_t n = 0; n < good.size(); ++n)
            tally(std::vector<uint8_t>(good.begin(), good.begin() + (std::ptrdiff_t) n));
        const size_t header_bytes = good.size() - 64;
        for (size_t i = 0; i < header_bytes; ++i)
            for (uint8_t v :
                 {uint8_t(0x00), uint8_t(0x01), uint8_t(0x7f), uint8_t(0x80), uint8_t(0xff), uint8_t(good[i] ^ 0x10)}) {
                if (v == good[i]) continue;
                std::vector<uint8_t> b = good;
                b[i] = v;
                tally(b);
            }
        std::printf("  (damaged copies: %d opened, %d refused)\n", opened, refused);
        check(refused > 0 && bad == 0, "damaged copies: each opens or is refused, in-bounds tensors read through");
    }
    std::printf(g_fail ? "gguf_reader_test: %d FAILED\n" : "gguf_reader_test: all passed\n", g_fail);
    return g_fail ? 1 : 0;
}
