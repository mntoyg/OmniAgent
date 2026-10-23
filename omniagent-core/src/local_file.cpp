#include "local_file.hpp"

#include <climits>
#include <cstring>
#include <fcntl.h>
#include <linux/magic.h>
#include <sys/stat.h>
#include <sys/vfs.h>
#include <unistd.h>

namespace omniagent::detail {
namespace {
bool local_filesystem(int fd) noexcept {
    struct statfs info {};
    if (fstatfs(fd, &info) != 0) {
        return false;
    }
    // Fail closed for NFS, SMB, FUSE, 9p, and unfamiliar filesystems.
    switch (info.f_type) {
        case EXT4_SUPER_MAGIC:
        case XFS_SUPER_MAGIC:
        case BTRFS_SUPER_MAGIC:
        case TMPFS_MAGIC:
        case RAMFS_MAGIC:
        case OVERLAYFS_SUPER_MAGIC:
            return true;
        default:
            return false;
    }
}
}

bool valid_config(const Config& c) noexcept {
    return c.context_tokens >= 8 && c.context_tokens <= 65536 &&
        c.batch_tokens > 0 && c.batch_tokens <= c.context_tokens &&
        c.threads > 0 && c.threads <= 256 &&
        c.max_prompt_bytes > 0 && c.max_prompt_bytes <= 16 * 1024 * 1024 &&
        c.max_output_bytes > 0 && c.max_output_bytes <= 16 * 1024 * 1024 &&
        c.max_model_bytes >= 24 && c.max_model_bytes <= (1ULL << 40);
}

OpenedFile open_local_file(std::string_view path, bool audit, std::uint64_t max_bytes) noexcept {
    if (path.size() < 2 || path.size() >= PATH_MAX || path.front() != '/' ||
        path.find_first_of("\\:") != path.npos || path.find('\0') != path.npos) {
        return {Error::invalid_path, -1};
    }
    int directory = open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (directory < 0) {
        return {Error::io, -1};
    }
    std::size_t start = 1;
    while (start < path.size()) {
        const auto slash = path.find('/', start);
        const bool final = slash == path.npos;
        const auto part = path.substr(start, final ? path.size() - start : slash - start);
        if (part.empty() || part == "." || part == ".." || part.size() > NAME_MAX) {
            close(directory);
            return {Error::invalid_path, -1};
        }
        char component[NAME_MAX + 1] {};
        std::memcpy(component, part.data(), part.size());
        const int flags = final
            ? ((audit ? O_WRONLY | O_CREAT | O_APPEND : O_RDONLY) | O_NONBLOCK)
            : O_RDONLY | O_DIRECTORY;
        const int next = openat(directory, component, flags | O_NOFOLLOW | O_CLOEXEC, 0600);
        close(directory);
        if (next < 0) {
            return {Error::io, -1};
        }
        if (final) {
            struct stat info {};
            Error error = Error::none;
            if (fstat(next, &info) != 0 || !S_ISREG(info.st_mode) || !local_filesystem(next)) {
                error = Error::invalid_path;
            } else if (!audit && (info.st_size < 24 || static_cast<std::uint64_t>(info.st_size) > max_bytes)) {
                error = info.st_size < 24 ? Error::invalid_model : Error::model_too_large;
            } else if (audit && (info.st_nlink != 1 || info.st_uid != geteuid() || (info.st_mode & 0077) != 0)) {
                error = Error::invalid_path;
            }
            if (error != Error::none) {
                close(next);
                return {error, -1};
            }
            return {Error::none, next};
        }
        directory = next;
        if (!local_filesystem(directory)) {
            close(directory);
            return {Error::invalid_path, -1};
        }
        start = slash + 1;
    }
    close(directory);
    return {Error::invalid_path, -1};
}
} // namespace omniagent::detail
