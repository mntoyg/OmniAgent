#include "omniagent/local_inference_engine.hpp"
#include "omniagent/secure_memory.hpp"
#include "local_file.hpp"
#include "llama.h"
#include "ggml.h"
#include "ggml-backend.h"

#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <exception>
#include <limits>
#include <memory>
#include <new>
#include <unistd.h>

namespace omniagent {
namespace {
std::once_flag backend_once;
void quiet_log(ggml_log_level, const char*, void*) noexcept {}
bool quiet_progress(float, void*) noexcept { return true; }
[[noreturn]] void quiet_abort(const char*) noexcept { std::_Exit(70); }
struct CloseStream {
    void operator()(FILE* stream) const noexcept { (void)fclose(stream); }
};

Error decode_status(int status) noexcept {
    switch (status) {
        case 0: return Error::none;
        case 1: return Error::context_limit;
        case 2: return Error::cancelled;
        default: return Error::backend;
    }
}
}

std::string_view error_message(Error error) noexcept {
    switch (error) {
        case Error::none: return "success";
        case Error::invalid_config: return "invalid engine limits";
        case Error::invalid_path: return "local regular POSIX file required";
        case Error::io: return "local file operation failed";
        case Error::model_too_large: return "model exceeds file size limit";
        case Error::invalid_model: return "unsupported or invalid GGUF model";
        case Error::not_loaded: return "model is not loaded";
        case Error::context_limit: return "request exceeds context limit";
        case Error::output_limit: return "request exceeds output limit";
        case Error::allocation: return "memory allocation failed";
        case Error::backend: return "local inference failed";
        case Error::cancelled: return "inference cancelled";
        case Error::log_io: return "local audit write failed";
    }
    return "unknown engine error";
}

LocalInferenceEngine::LocalInferenceEngine(Config config) noexcept : config_(config) {}
LocalInferenceEngine::~LocalInferenceEngine() noexcept { (void)unload(); }

bool LocalInferenceEngine::loaded() const noexcept {
    std::lock_guard lock(mutex_);
    return context_ != nullptr;
}
void LocalInferenceEngine::cancel() noexcept { cancelled_.store(true, std::memory_order_relaxed); }
bool LocalInferenceEngine::aborted(void* engine) noexcept {
    return static_cast<LocalInferenceEngine*>(engine)->cancelled_.load(std::memory_order_relaxed);
}

Error LocalInferenceEngine::load(std::string_view model_path, std::string_view audit_path) noexcept {
    std::lock_guard lock(mutex_);
    const Error previous = unload_locked();
    if (previous != Error::none) { return previous; }
    if (!detail::valid_config(config_)) { return Error::invalid_config; }
    const auto file = detail::open_local_file(model_path, false, config_.max_model_bytes);
    if (file.error != Error::none) { return file.error; }
    FILE* raw = fdopen(file.fd, "rb");
    if (raw == nullptr) { close(file.fd); return Error::io; }
    const std::unique_ptr<FILE, CloseStream> stream(raw);
    // No stdio read-ahead allocation containing weights remains in libc.
    if (setvbuf(raw, nullptr, _IONBF, 0) != 0) { return Error::io; }
    unsigned char header[8] {};
    const auto read = fread(header, 1, sizeof(header), raw);
    if (read != sizeof(header) || std::memcmp(header, "GGUF", 4) != 0 ||
        (header[4] != 2 && header[4] != 3) || header[5] || header[6] || header[7]) {
        return Error::invalid_model;
    }
    rewind(raw);
    try {
        std::call_once(backend_once, [] {
            llama_log_set(quiet_log, nullptr);
            ggml_log_set(quiet_log, nullptr);
            ggml_set_abort_callback(quiet_abort);
            std::set_terminate([] { std::_Exit(70); });
            llama_backend_init();
        });
        if (ggml_backend_reg_count() != 1 ||
            std::strcmp(ggml_backend_reg_name(ggml_backend_reg_get(0)), "CPU") != 0) {
            return Error::backend;
        }
        auto mp = llama_model_default_params();
        ggml_backend_dev_t cpu_only[] = { nullptr };
        mp.devices = cpu_only;
        mp.n_gpu_layers = 0;
        mp.load_mode = LLAMA_LOAD_MODE_NONE; // No read-only mappings that cannot be wiped.
        mp.lazy_mode = LLAMA_LAZY_MODE_OFF;
        mp.progress_callback = quiet_progress;
        mp.check_tensors = true;
        mp.use_extra_bufts = false;
        mp.load_mtp = false;
        model_ = llama_model_load_from_file_ptr(raw, mp);
        if (model_ == nullptr || !llama_model_has_decoder(model_) || llama_model_has_encoder(model_) ||
            llama_vocab_n_tokens(llama_model_get_vocab(model_)) <= 0) {
            (void)unload_locked();
            return Error::invalid_model;
        }
        auto cp = llama_context_default_params();
        cp.n_ctx = config_.context_tokens;
        cp.n_batch = config_.batch_tokens;
        cp.n_ubatch = config_.batch_tokens;
        cp.n_seq_max = 1;
        cp.n_outputs_max = 1;
        cp.n_outputs_max_per_seq = 1;
        cp.n_threads = static_cast<std::int32_t>(config_.threads);
        cp.n_threads_batch = cp.n_threads;
        cp.offload_kqv = false;
        cp.op_offload = false;
        cp.embeddings = false;
        cp.no_perf = true;
        cp.abort_callback = aborted;
        cp.abort_callback_data = this;
        cancelled_.store(false, std::memory_order_relaxed);
        context_ = llama_init_from_model(model_, cp);
        if (context_ == nullptr || llama_get_memory(context_) == nullptr ||
            llama_n_ctx(context_) < config_.context_tokens) {
            (void)unload_locked();
            return Error::backend;
        }
        tokens_ = new std::int32_t[config_.context_tokens] {};
        piece_capacity_ = config_.max_output_bytes;
        piece_ = new char[piece_capacity_] {};
        if (!audit_path.empty()) {
            const auto log = detail::open_local_file(audit_path, true, 0);
            if (log.error != Error::none) { (void)unload_locked(); return log.error; }
            audit_fd_ = log.fd;
        }
        const auto error = audit(Error::none, 0, 0);
        if (error != Error::none) { (void)unload_locked(); }
        return error;
    } catch (const std::bad_alloc&) {
        (void)unload_locked();
        return Error::allocation;
    } catch (...) {
        (void)unload_locked();
        return Error::backend;
    }
}

void LocalInferenceEngine::clear_request() noexcept {
    if (context_ != nullptr) {
        llama_synchronize(context_);
        llama_memory_clear(llama_get_memory(context_), true);
        auto* logits = llama_get_logits(context_);
        if (logits != nullptr) {
            const auto count = llama_vocab_n_tokens(llama_model_get_vocab(model_));
            secure_zero(logits, static_cast<std::size_t>(count) * sizeof(float));
        }
    }
    if (tokens_ != nullptr) { secure_zero(tokens_, config_.context_tokens * sizeof(*tokens_)); }
    if (piece_ != nullptr) { secure_zero(piece_, piece_capacity_); }
}

Error LocalInferenceEngine::unload_locked() noexcept {
    // Synchronize before wiping, then free context before its model.
    clear_request();
    if (context_ != nullptr) { llama_free(context_); context_ = nullptr; }
    if (model_ != nullptr) { llama_model_free(model_); model_ = nullptr; }
    delete[] tokens_; tokens_ = nullptr;
    delete[] piece_; piece_ = nullptr; piece_capacity_ = 0;
    const auto error = audit(Error::none, 0, 0);
    if (audit_fd_ >= 0) { close(audit_fd_); audit_fd_ = -1; }
    return error;
}
Error LocalInferenceEngine::unload() noexcept {
    cancel();
    std::lock_guard lock(mutex_);
    return unload_locked();
}

Error LocalInferenceEngine::audit(Error error, std::size_t bytes, std::uint32_t tokens) noexcept {
    if (audit_fd_ < 0) { return Error::none; }
    char record[96] {};
    const int count = std::snprintf(record, sizeof(record), "status=%u bytes=%zu tokens=%u\n",
        static_cast<unsigned>(error), bytes, tokens);
    if (count <= 0 || static_cast<std::size_t>(count) >= sizeof(record)) { return Error::log_io; }
    std::size_t offset = 0;
    while (offset < static_cast<std::size_t>(count)) {
        const auto result = write(audit_fd_, record + offset, static_cast<std::size_t>(count) - offset);
        if (result < 0 && errno == EINTR) { continue; }
        if (result <= 0) { return Error::log_io; }
        offset += static_cast<std::size_t>(result);
    }
    return Error::none;
}

Generation LocalInferenceEngine::generate(std::string_view prompt, std::uint32_t max_tokens,
                                          std::span<char> output) noexcept {
    std::lock_guard lock(mutex_);
    Generation result;
    try { result = generate_locked(prompt, max_tokens, output); }
    catch (const std::bad_alloc&) { result.error = Error::allocation; }
    catch (...) { result.error = Error::backend; }
    clear_request(); // Includes aborted/partial decode and every exception.
    const auto log_error = audit(result.error, result.bytes, result.tokens);
    if (log_error != Error::none) { result.error = log_error; }
    if (result.error != Error::none) {
        secure_zero(output.data(), output.size());
        result.bytes = 0;
        result.tokens = 0;
        result.stop = Stop::none;
    }
    return result;
}

Generation LocalInferenceEngine::generate_locked(std::string_view prompt, std::uint32_t max_tokens,
                                                 std::span<char> output) {
    if (context_ == nullptr) { return {Error::not_loaded}; }
    if (prompt.empty() || prompt.size() > config_.max_prompt_bytes ||
        max_tokens == 0 || max_tokens > config_.context_tokens) { return {Error::context_limit}; }
    if (output.empty() || output.size() > config_.max_output_bytes) { return {Error::output_limit}; }
    cancelled_.store(false, std::memory_order_relaxed);
    clear_request();
    const auto* vocab = llama_model_get_vocab(model_);
    const auto count = llama_tokenize(vocab, prompt.data(), static_cast<std::int32_t>(prompt.size()),
        tokens_, static_cast<std::int32_t>(config_.context_tokens), true, false);
    if (count <= 0 || static_cast<std::uint32_t>(count) > config_.context_tokens - max_tokens) {
        return {Error::context_limit};
    }
    for (std::int32_t offset = 0; offset < count;) {
        if (aborted(this)) { return {Error::cancelled}; }
        const auto batch = std::min(count - offset, static_cast<std::int32_t>(config_.batch_tokens));
        const auto error = decode_status(llama_decode(context_, llama_batch_get_one(tokens_ + offset, batch)));
        if (error != Error::none) { return {error}; }
        offset += batch;
    }
    Generation result;
    const auto n_vocab = llama_vocab_n_tokens(vocab);
    for (std::uint32_t step = 0; step < max_tokens; ++step) {
        if (aborted(this)) { return {Error::cancelled}; }
        const float* logits = llama_get_logits_ith(context_, -1);
        if (logits == nullptr) { return {Error::backend}; }
        llama_token token = 0;
        float best = -std::numeric_limits<float>::infinity();
        for (llama_token index = 0; index < n_vocab; ++index) {
            if (!std::isfinite(logits[index])) { return {Error::backend}; }
            if (logits[index] > best) { best = logits[index]; token = index; }
        }
        if (llama_vocab_is_eog(vocab, token)) { result.stop = Stop::end_of_generation; return result; }
        const auto bytes = llama_token_to_piece(vocab, token, piece_,
            static_cast<std::int32_t>(piece_capacity_), 0, false);
        if (bytes < 0 || static_cast<std::size_t>(bytes) > output.size() - result.bytes) {
            return {Error::output_limit};
        }
        std::memcpy(output.data() + result.bytes, piece_, static_cast<std::size_t>(bytes));
        result.bytes += static_cast<std::size_t>(bytes);
        ++result.tokens;
        secure_zero(piece_, piece_capacity_);
        if (step + 1 < max_tokens) {
            tokens_[count + step] = token;
            const auto error = decode_status(llama_decode(context_, llama_batch_get_one(tokens_ + count + step, 1)));
            if (error != Error::none) { return {error}; }
        }
    }
    result.stop = Stop::token_limit;
    return result;
}
} // namespace omniagent
