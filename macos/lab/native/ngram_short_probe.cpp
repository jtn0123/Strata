// CPU-only probe linked to the exact existing engine's ngram-map object.
// No model, backend, GPU, socket or tokenizer is initialized.
#include "ngram-map.h"
#include "log.h"

#include <cstdlib>
#include <iostream>
#include <stdexcept>

int common_log_get_verbosity_thold() { return -1; }
common_log * common_log_main() { return nullptr; }
void common_log_add(common_log *, ggml_log_level, const char *, ...) {}
void ggml_abort(const char *, int, const char *, ...) { std::abort(); }

int main() {
    int cases = 0;
    for (uint16_t key : {uint16_t(4), uint16_t(12), uint16_t(16)}) {
        for (uint16_t width : {uint16_t(1), uint16_t(2), uint16_t(3)}) {
            llama_tokens history = {900};
            for (int token = 1; token <= key; ++token) history.push_back(token);
            history.insert(history.end(), {41, 42, 43, 44, 45, 901});
            for (int token = 1; token < key; ++token) history.push_back(token);
            const auto simple = common_ngram_simple_draft({key, width}, history, key);
            if (!simple.empty()) throw std::runtime_error("simple unexpectedly supports short proposals");
            common_ngram_map map(key, width, true, 1);
            common_ngram_map_begin(map, history);
            llama_tokens draft;
            common_ngram_map_draft(map, history, key, draft);
            const llama_tokens expected({41, 42, 43});
            if (draft != llama_tokens(expected.begin(), expected.begin() + width)) {
                throw std::runtime_error("map did not produce the exact bounded continuation");
            }
            ++cases;
            common_ngram_map missing(key, width, true, 1);
            common_ngram_map_begin(missing, history);
            draft.clear();
            common_ngram_map_draft(missing, history, 999, draft);
            if (!draft.empty()) throw std::runtime_error("nonmatching history invented a proposal");
            ++cases;
        }
    }
    std::cout << "{\"status\":\"passed\",\"cases\":" << cases
              << ",\"simple_short_drafts\":0,\"map_maximum_width\":3,\"models_loaded\":false,\"gpu_tests\":false}\n";
}
