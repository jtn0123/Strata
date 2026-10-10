#include "llama.h"
#include <nlohmann/json.hpp>
#include <cstdio>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
using json=nlohmann::json;
static void quiet(enum ggml_log_level, const char *, void *) {}
int main(int argc,char **argv) {
    if (argc!=2) return 2;
    llama_log_set(quiet,nullptr);
    llama_backend_init();
    auto params=llama_model_default_params();
    params.vocab_only=true; params.n_gpu_layers=0;
    auto *model=llama_model_load_from_file(argv[1],params);
    if (!model) return 3;
    const auto *vocab=llama_model_get_vocab(model);
    json in; std::cin>>in;
    std::vector<llama_token> ids;
    if (in.contains("text")) {
        std::string text=in.at("text").get<std::string>();
        ids.resize(text.size()+128);
        int n=llama_tokenize(vocab,text.data(),text.size(),ids.data(),ids.size(),false,true);
        if (n<0) throw std::runtime_error("Unexpected token buffer overflow");
        ids.resize(n);
    } else ids=in.at("tokens").get<std::vector<llama_token>>();
    std::vector<char> buffer(65536);
    int n=llama_detokenize(vocab,ids.data(),ids.size(),buffer.data(),buffer.size(),false,true);
    if (n<0) throw std::runtime_error("Unexpected text buffer overflow");
    std::string text(buffer.data(),n);
    if (in.contains("text") && text!=in.at("text").get<std::string>())
        throw std::runtime_error("Exact input roundtrip changed");
    std::cout<<json({{"tokens",ids},{"text",text},{"vocabulary_only",true},{"weights_loaded",false}}).dump()<<'\n';
    llama_model_free(model);
    llama_backend_free();
}
