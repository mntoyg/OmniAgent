# omniagent-core

A native C++20 GGUF inference runtime using the local llama.cpp revision
`869034b4bb93a425ea989d30fc3d000f5a461d58`. The Python/Ollama agent is separate.

## Build offline

Use Linux/glibc, GCC or Clang, the GNU linker, CMake and Python 3.
On Windows, build in a local WSL distribution with these tools installed.
Supply the dependency locally; CMake does not download it (the missing-source
and changed-header configure checks are recorded in Brief 04).

```sh
cmake -S omniagent-core -B omniagent-core/build -DCMAKE_BUILD_TYPE=Release \
  -DLLAMA_SOURCE_DIR=/absolute/path/to/local/llama.cpp
cmake --build omniagent-core/build --parallel
ctest --test-dir omniagent-core/build --output-on-failure --no-tests=error
```

The default dependency directory is `models/llama.cpp`. The API fingerprint
expects the canonical LF header, SHA256 `d5cf9203bea63b575e76cba4881f29cfd1b611451578b01582b75b72ecbb04bc`. CRLF working trees are refused: `core.autocrlf=true` or reading a Windows checkout through `/mnt` changes the bytes. This is not verification of the complete dependency source; supply a trusted checkout.
For a build without test executables, pass `-DOMNI_BUILD_TESTS=OFF`.
Link applications with the `omniagent_core` CMake target. Use a dedicated
inference process; do not combine it with another allocator, llama.cpp
installation, or overrides of the global logging hooks.

## Use

```cpp
#include <array>
#include "omniagent/local_inference_engine.hpp"
#include "omniagent/secure_memory.hpp"

omniagent::Config config;
config.context_tokens = 2048;
config.batch_tokens = 128;
config.threads = 4;
omniagent::LocalInferenceEngine engine(config);

const auto error = engine.load("/opt/models/omniagent.gguf");
if (error != omniagent::Error::none) {
    // Handle the error in the caller.
    return;
}
std::array<char, 4096> output{};
const auto result = engine.generate("Hello", 128, output);
if (result.error == omniagent::Error::none) {
    // Consume exactly result.bytes bytes.
}
omniagent::secure_zero(output.data(), output.size());
engine.unload();
```

Apply the model's chat template before calling `generate`. Input and successful
output belong to the caller; clear those copies and join engine users before
destroying the engine.

## Tested security boundaries

The named CTest targets below define the verified scope. Each claim here has a
claim-to-test entry in `docs/pm/brief-04-the-fourth-gate.md`.

- `core` rejects relative paths, URIs, drive-letter paths, backslashes, colons,
  NULs, empty components, `.` and `..`; it rejects parent/final symlinks, FIFOs
  and `/proc/version`. Its fixtures are copied to `/tmp` before loading.
- `core` rejects malformed GGUF, oversized model files, out-of-range context
  configuration and thread counts 0 and 257. Context/prompt and output limits
  return errors. Output overflow after partial generation clears the complete
  supplied output span.
- `core` produces exactly `aaa` over ten repetitions and forty requests from
  four threads sharing one engine. It distinguishes EOS from token-limit stops,
  exercises cancellation followed by successful reuse and concurrent unload,
  and checks repeated unload. It inspects cleared token/piece buffers, exposed
  logits and empty KV sequence positions after successful generation and
  cancellation. These checks do not inspect every byte of backend KV storage.
- `core` rejects group/world-readable audit files, multiply linked audit files
  and final audit symlinks. It verifies appended records contain exactly numeric
  status, byte and token fields. A failed audit write returns `log_io` and wipes
  the supplied output. The backend abort child exits 70 with empty stdout/stderr.
- `secure_heap` observes zeroed allocations before real release, including
  allocator padding, wrapped free/realloc, C++ array delete and aligned scalar
  delete. Failed realloc preserves the original allocation. It does not trace
  every backend allocation to a release path.
- `core` checks that initialization with `GGML_BACKEND_PATH` set and explicit
  `ggml_backend_load` do not execute its local shared-library probe.
  `offline_imports` rejects the networking, HTTP/TLS and dynamic-loading symbols
  enumerated in `tests/check_imports.cmake` from the test executable's undefined
  imports. This check does not establish a complete absence of network access.

## Limits

This contract covers owned heap buffers during normal error handling and
destruction. It does not promise erasure after SIGKILL, crashes, power loss, or
OS swap/core dumps, and does not clear kernel file caches or CPU register/stack
copies. It does not provide process isolation or locked pages. Those stronger
requirements need deployment controls. Limits bound prompt bytes, output bytes,
tokens, threads, and model **file size**, not total backend peak RAM. A trusted
GGUF is required: llama.cpp may abort on a fatal internal assertion, and C++
exception handling cannot turn an abort into an error code. The fatal callback
and terminate hook exit with code 70 without printing backend text or addresses.
The host should
apply process memory limits and supervise a dedicated worker if that failure
boundary is required.

## Verification

`make_tiny_gguf` synthesizes deterministic Llama GGUF fixtures with Python's
standard library. `core` uses them for real inference; `secure_heap` and
`offline_imports` cover the boundaries above. These fixtures do not evaluate
the project's Qwen model quality or performance.
