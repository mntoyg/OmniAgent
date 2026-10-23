"""Write a deterministic, real decoder GGUF using only the Python standard library."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

ALIGNMENT = 32
WIDTH = 8
HIDDEN = 16
VOCABULARY = ["<unk>", "<s>", "</s>", "▁", "a", "b", "c", "d"]


def string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack("<Q", len(encoded)) + encoded


def u32(key: str, value: int) -> bytes:
    return string(key) + struct.pack("<II", 4, value)


def f32(key: str, value: float) -> bytes:
    return string(key) + struct.pack("<If", 6, value)


def text(key: str, value: str) -> bytes:
    return string(key) + struct.pack("<I", 8) + string(value)


def array(key: str, item_type: int, values: list[bytes]) -> bytes:
    return string(key) + struct.pack("<IIQ", 9, item_type, len(values)) + b"".join(values)


def write_model(path: Path, *, eos: bool = False) -> None:
    """Produce logits that always select 'a' (or EOS), with nonzero KV state."""
    metadata = [
        text("general.architecture", "llama"),
        u32("general.alignment", ALIGNMENT),
        u32("llama.context_length", 8192),
        u32("llama.embedding_length", WIDTH),
        u32("llama.block_count", 1),
        u32("llama.feed_forward_length", HIDDEN),
        u32("llama.attention.head_count", 2),
        u32("llama.attention.head_count_kv", 1),
        u32("llama.rope.dimension_count", 4),
        f32("llama.attention.layer_norm_rms_epsilon", 1e-5),
        text("tokenizer.ggml.model", "llama"),
        array("tokenizer.ggml.tokens", 8, [string(token) for token in VOCABULARY]),
        array("tokenizer.ggml.scores", 6, [struct.pack("<f", 0.0)] * len(VOCABULARY)),
        array(
            "tokenizer.ggml.token_type", 5, [struct.pack("<i", t) for t in [2, 3, 3, 1, 1, 1, 1, 1]]
        ),
        u32("tokenizer.ggml.bos_token_id", 1),
        u32("tokenizer.ggml.eos_token_id", 2),
        u32("tokenizer.ggml.unknown_token_id", 0),
    ]
    selected = 2 if eos else 4
    tensors: list[tuple[str, list[int], list[float]]] = [
        ("token_embd.weight", [WIDTH, len(VOCABULARY)], [0.25] * (WIDTH * len(VOCABULARY))),
        ("output_norm.weight", [WIDTH], [1.0] * WIDTH),
        (
            "output.weight",
            [WIDTH, len(VOCABULARY)],
            [
                1.0 if row == selected else 0.0
                for row in range(len(VOCABULARY))
                for _ in range(WIDTH)
            ],
        ),
        ("blk.0.attn_norm.weight", [WIDTH], [1.0] * WIDTH),
        ("blk.0.attn_q.weight", [WIDTH, WIDTH], [0.01] * (WIDTH * WIDTH)),
        ("blk.0.attn_k.weight", [WIDTH, WIDTH // 2], [0.01] * (WIDTH * WIDTH // 2)),
        ("blk.0.attn_v.weight", [WIDTH, WIDTH // 2], [0.01] * (WIDTH * WIDTH // 2)),
        ("blk.0.attn_output.weight", [WIDTH, WIDTH], [0.0] * (WIDTH * WIDTH)),
        ("blk.0.ffn_norm.weight", [WIDTH], [1.0] * WIDTH),
        ("blk.0.ffn_gate.weight", [WIDTH, HIDDEN], [0.0] * (WIDTH * HIDDEN)),
        ("blk.0.ffn_up.weight", [WIDTH, HIDDEN], [0.0] * (WIDTH * HIDDEN)),
        ("blk.0.ffn_down.weight", [HIDDEN, WIDTH], [0.0] * (WIDTH * HIDDEN)),
    ]
    descriptions = bytearray()
    data = bytearray()
    for name, dimensions, values in tensors:
        data.extend(b"\0" * (-len(data) % ALIGNMENT))
        descriptions.extend(string(name) + struct.pack("<I", len(dimensions)))
        descriptions.extend(struct.pack("<" + "Q" * len(dimensions), *dimensions))
        descriptions.extend(struct.pack("<IQ", 0, len(data)))  # GGML_TYPE_F32
        data.extend(struct.pack("<" + "f" * len(values), *values))
    header = struct.pack("<4sIQQ", b"GGUF", 3, len(tensors), len(metadata))
    payload = header + b"".join(metadata) + descriptions
    path.write_bytes(payload + b"\0" * (-len(payload) % ALIGNMENT) + data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write_model(args.output)
    write_model(args.output.with_suffix(".eos.gguf"), eos=True)
