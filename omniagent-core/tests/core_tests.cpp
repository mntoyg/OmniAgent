#include "omniagent/local_inference_engine.hpp"
#include "omniagent/secure_memory.hpp"
#include "local_file.hpp"
#include "llama.h"
#include "ggml-backend.h"
#include <algorithm>
#include <array>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <filesystem>
#include <fstream>
#include <string>
#include <thread>
#include <vector>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

namespace fs = std::filesystem;
using omniagent::Error;
using omniagent::LocalInferenceEngine;
#define CHECK(condition) do { if (!(condition)) { std::fprintf(stderr, "Failed at line %d: %s\n", __LINE__, #condition); std::exit(1); } } while (false)

namespace omniagent {
struct EngineTestAccess {
    static bool clean(const LocalInferenceEngine& engine) {
        if (engine.context_ == nullptr) {
            return engine.model_ == nullptr && engine.tokens_ == nullptr && engine.piece_ == nullptr;
        }
        const auto* logits = llama_get_logits(engine.context_);
        const auto size = llama_vocab_n_tokens(llama_model_get_vocab(engine.model_));
        return llama_memory_seq_pos_max(llama_get_memory(engine.context_), 0) == -1 &&
            std::all_of(engine.tokens_, engine.tokens_ + engine.config_.context_tokens,
                [](auto token) { return token == 0; }) &&
            std::all_of(engine.piece_, engine.piece_ + engine.piece_capacity_,
                [](auto byte) { return byte == 0; }) &&
            (logits == nullptr || std::all_of(logits, logits + size, [](auto logit) { return logit == 0; }));
    }
    static void break_audit(LocalInferenceEngine& engine) {
        CHECK(close(engine.audit_fd_) == 0);
        engine.audit_fd_ = open("/dev/null", O_RDONLY | O_CLOEXEC);
        CHECK(engine.audit_fd_ >= 0);
    }
};
}

bool wiped(const std::array<char, 64>& output) {
    return std::all_of(output.begin(), output.end(), [](char c) { return c == 0; });
}

int main(int argc, char** argv) {
    CHECK(argc == 3);
    char directory[] = "/tmp/omniagent-core-XXXXXX";
    CHECK(mkdtemp(directory) != nullptr);
    const fs::path root(directory);
    struct Cleanup { fs::path root; ~Cleanup() { fs::remove_all(root); } } cleanup{root};
    const auto model = (root / "model.gguf").string();
    const auto eos_model = (root / "eos.gguf").string();
    const auto log = (root / "audit.log").string();
    fs::copy_file(argv[1], model);
    auto eos_source = fs::path(argv[1]); eos_source.replace_extension(".eos.gguf");
    fs::copy_file(eos_source, eos_model);
    const auto plugin_marker = (root / "plugin-was-loaded").string();
    CHECK(setenv("GGML_BACKEND_PATH", argv[2], 1) == 0);
    CHECK(setenv("OMNI_PROBE_FILE", plugin_marker.c_str(), 1) == 0);

    omniagent::Config config;
    config.context_tokens = 64;
    config.batch_tokens = 4;
    config.threads = 2;
    config.max_output_bytes = 64;
    LocalInferenceEngine engine(config);
    std::array<char, 64> output;
    output.fill('X');
    CHECK(engine.generate("a", 3, output).error == Error::not_loaded);
    CHECK(wiped(output));
    CHECK(engine.load("https://example.com/model.gguf") == Error::invalid_path);
    CHECK(engine.load("model.gguf") == Error::invalid_path);
    CHECK(engine.load("//host/share/model.gguf") == Error::invalid_path);
    CHECK(engine.load("/tmp/../tmp/model.gguf") == Error::invalid_path);
    CHECK(engine.load("/tmp//model.gguf") == Error::invalid_path);
    CHECK(engine.load(std::string_view("/tmp/\0model", 11)) == Error::invalid_path);
    CHECK(engine.load("C:\\model.gguf") == Error::invalid_path);
    // Both model and audit boundaries reject each path syntax class.
    for (const std::string_view path : {"", "/", "relative", "/tmp/./model.gguf",
             "/tmp/a\\b", "/tmp/a:b", "/tmp/", "/tmp//model.gguf"}) {
        CHECK(omniagent::detail::open_local_file(path, false, config.max_model_bytes).error == Error::invalid_path);
        CHECK(omniagent::detail::open_local_file(path, true, 0).error == Error::invalid_path);
    }
    CHECK(engine.load("/proc/version") == Error::invalid_path);
    CHECK(engine.load("/dev/zero") == Error::invalid_path);
    fs::create_symlink(model, root / "link.gguf");
    CHECK(engine.load((root / "link.gguf").string()) == Error::io);
    fs::create_directory_symlink(root, root / "alias");
    CHECK(engine.load((root / "alias/model.gguf").string()) == Error::io);
    CHECK(mkfifo((root / "fifo").c_str(), 0600) == 0);
    CHECK(engine.load((root / "fifo").string()) == Error::invalid_path);
    { std::ofstream bad(root / "bad.gguf"); bad << std::string(24, 'X'); }
    CHECK(engine.load((root / "bad.gguf").string()) == Error::invalid_model);
    CHECK(!engine.loaded());
    auto invalid = config; invalid.context_tokens = UINT32_MAX;
    CHECK(LocalInferenceEngine(invalid).load(model) == Error::invalid_config);
    for (const auto threads : {0U, 257U}) {
        auto bad_threads = config;
        bad_threads.threads = threads;
        CHECK(LocalInferenceEngine(bad_threads).load(model) == Error::invalid_config);
    }
    auto small = config; small.max_model_bytes = 24;
    CHECK(LocalInferenceEngine(small).load(model) == Error::model_too_large);

    CHECK(engine.load(model, log) == Error::none);
    CHECK(ggml_backend_load(argv[2]) == nullptr);
    CHECK(!fs::exists(plugin_marker));
    CHECK(engine.loaded());
    for (int run = 0; run < 10; ++run) {
        const auto result = engine.generate("a", 3, output);
        CHECK(result.error == Error::none);
        CHECK(result.stop == omniagent::Stop::token_limit);
        CHECK(result.tokens == 3 && result.bytes == 3);
        CHECK(std::string_view(output.data(), result.bytes) == "aaa");
        CHECK(omniagent::EngineTestAccess::clean(engine));
    }
    output.fill('X');
    CHECK(engine.generate("a", 3, std::span<char>(output.data(), 1)).error == Error::output_limit);
    CHECK(output[0] == 0);
    // Overflow after partial output must erase the entire supplied span.
    std::array<char, 2> partial {'X', 'X'};
    CHECK(engine.generate("a", 3, partial).error == Error::output_limit);
    CHECK(std::all_of(partial.begin(), partial.end(), [](char c) { return c == 0; }));
    CHECK(omniagent::EngineTestAccess::clean(engine));
    output.fill('X');
    CHECK(engine.generate("a", 64, output).error == Error::context_limit);
    CHECK(wiped(output));
    output.fill('X');
    CHECK(engine.generate("", 3, output).error == Error::context_limit);
    CHECK(wiped(output));
    CHECK(engine.generate(std::string(1024 * 1024 + 1, 'a'), 1, output).error == Error::context_limit);

    // Serialization gives deterministic independent requests, without shared KV.
    std::atomic<int> correct{0};
    std::vector<std::thread> workers;
    for (int thread = 0; thread < 4; ++thread) {
        workers.emplace_back([&] {
            std::array<char, 64> local {};
            for (int run = 0; run < 10; ++run) {
                const auto result = engine.generate("b", 3, local);
                if (result.error == Error::none && std::string_view(local.data(), result.bytes) == "aaa") { ++correct; }
            }
        });
    }
    for (auto& worker : workers) { worker.join(); }
    CHECK(correct == 40);
    CHECK(engine.unload() == Error::none);
    CHECK(engine.unload() == Error::none);
    CHECK(!engine.loaded());
    CHECK(omniagent::EngineTestAccess::clean(engine));
    { std::ifstream audit(log); const std::string content((std::istreambuf_iterator<char>(audit)), {});
      CHECK(content.find("status=0 bytes=3 tokens=3") != content.npos);
      CHECK(content.find("aaa") == content.npos && content.find("0x") == content.npos);
      CHECK(content.find(model) == content.npos); }
    {
        std::ifstream audit(log);
        std::string line;
        std::size_t records = 0;
        while (std::getline(audit, line)) {
            unsigned status = 0, tokens = 0;
            std::size_t bytes = 0;
            int consumed = 0;
            CHECK(std::sscanf(line.c_str(), "status=%u bytes=%zu tokens=%u%n",
                &status, &bytes, &tokens, &consumed) == 3);
            CHECK(consumed == static_cast<int>(line.size()));
            CHECK(status <= static_cast<unsigned>(Error::log_io));
            ++records;
        }
        CHECK(records > 40); // Older records survived subsequent writes.
    }
    for (const auto permissions : {0640, 0604}) {
        CHECK(chmod(log.c_str(), permissions) == 0);
        CHECK(engine.load(model, log) == Error::invalid_path);
        CHECK(!engine.loaded());
    }
    fs::create_hard_link(log, root / "log-alias");
    CHECK(chmod(log.c_str(), 0600) == 0);
    CHECK(engine.load(model, log) == Error::invalid_path);
    fs::create_symlink(root / "new-log", root / "log-link");
    CHECK(engine.load(model, (root / "log-link").string()) == Error::io);

    CHECK(engine.load(eos_model) == Error::none);
    const auto eos = engine.generate("a", 3, output);
    CHECK(eos.error == Error::none && eos.stop == omniagent::Stop::end_of_generation);
    CHECK(eos.tokens == 0 && eos.bytes == 0);
    CHECK(engine.unload() == Error::none);

    // Cancel during a deliberately long CPU prefill; no partial output survives.
    auto long_config = config;
    long_config.context_tokens = 8192;
    long_config.batch_tokens = 1024;
    long_config.threads = 1;
    LocalInferenceEngine long_engine(long_config);
    CHECK(long_engine.load(model) == Error::none);
    std::string prompt(4000, 'a');
    std::atomic<bool> started{false}, finished{false};
    omniagent::Generation cancelled;
    output.fill('X');
    std::thread generator([&] {
        started = true;
        cancelled = long_engine.generate(prompt, 32, output);
        finished = true;
    });
    while (!started) { std::this_thread::yield(); }
    while (!finished) { long_engine.cancel(); std::this_thread::yield(); }
    generator.join();
    CHECK(cancelled.error == Error::cancelled);
    CHECK(omniagent::EngineTestAccess::clean(long_engine));
    CHECK(wiped(output));
    CHECK(long_engine.generate("a", 3, output).error == Error::none);
    CHECK(omniagent::EngineTestAccess::clean(long_engine));
    CHECK(long_engine.unload() == Error::none);

    CHECK(engine.load(model) == Error::none);
    std::atomic<bool> race_done{false};
    std::thread racing([&] {
        std::array<char, 64> local {};
        for (int run = 0; run < 30; ++run) {
            const auto result = engine.generate("a", 3, local);
            CHECK(result.error == Error::none || result.error == Error::not_loaded || result.error == Error::cancelled);
        }
        race_done = true;
    });
    CHECK(engine.unload() == Error::none);
    racing.join();
    CHECK(race_done && !engine.loaded());
    CHECK(engine.load(model, (root / "failure.log").string()) == Error::none);
    omniagent::EngineTestAccess::break_audit(engine);
    output.fill('X');
    CHECK(engine.generate("a", 3, output).error == Error::log_io);
    CHECK(wiped(output));
    CHECK(omniagent::EngineTestAccess::clean(engine));
    CHECK(engine.unload() == Error::log_io);
    // Fatal backend diagnostics must not print even a deliberately supplied address.
    for (const bool terminate : {false, true}) {
        int diagnostic_pipe[2];
        CHECK(pipe(diagnostic_pipe) == 0);
        const auto child = fork();
        CHECK(child >= 0);
        if (child == 0) {
            close(diagnostic_pipe[0]);
            CHECK(dup2(diagnostic_pipe[1], STDERR_FILENO) >= 0);
            CHECK(dup2(diagnostic_pipe[1], STDOUT_FILENO) >= 0);
            close(diagnostic_pipe[1]);
            if (terminate) { std::terminate(); }
            ggml_abort("PRIVATE_PATH", 123, "private prompt and addr=%p", static_cast<void*>(&engine));
        }
        close(diagnostic_pipe[1]);
        char diagnostic[128];
        CHECK(read(diagnostic_pipe[0], diagnostic, sizeof(diagnostic)) == 0);
        close(diagnostic_pipe[0]);
        int child_status = 0;
        CHECK(waitpid(child, &child_status, 0) == child);
        CHECK(WIFEXITED(child_status) && WEXITSTATUS(child_status) == 70);
    }
    for (unsigned code = 0; code <= static_cast<unsigned>(Error::log_io); ++code) {
        CHECK(omniagent::error_message(static_cast<Error>(code)).size() < 64);
    }
    std::puts("Core: GGUF inference, 10 repetitions, 40 concurrent requests, limits, paths, audit, EOS, cancellation, unload passed");
}
