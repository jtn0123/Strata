"""Validate and explicitly select the pinned multilingual draft vocabulary."""
import json
import os
from pathlib import Path
import struct

from engines import sha256
from lab import ROOT


def read_ids(data, full_count):
    if not data or len(data) % 4 or len(data) > full_count * 4:
        raise ValueError("Vocabulary must contain complete int32 token ids")
    ids = [item[0] for item in struct.iter_unpack("<i", data)]
    if any(token < 0 or token >= full_count for token in ids):
        raise ValueError("Vocabulary contains an out-of-range token id")
    if len(set(ids)) != len(ids):
        raise ValueError("Vocabulary contains duplicate token ids")
    return ids


def vocabulary_info(root=ROOT):
    info = json.loads((root / "config/draft_vocab_experiment.json").read_text())["vocabulary"]
    path = root / info["path"]
    if sha256(path) != info["sha256"]:
        raise RuntimeError("Draft vocabulary hash differs from the pinned manifest")
    ids = read_ids(path.read_bytes(), info["full_count"])
    if len(ids) != info["count"]:
        raise RuntimeError("Draft vocabulary token count differs from the manifest")
    return dict(info)


def experiment_environment(engine, mode="off", root=ROOT):
    env = dict(os.environ)
    env.pop("MELD_DRAFT_VOCAB", None)
    if mode == "off":
        return env, None
    if mode != "106k" or engine != "draft-vocab":
        raise ValueError("The 106k vocabulary requires the isolated draft-vocab engine")
    info = vocabulary_info(root)
    env["MELD_DRAFT_VOCAB"] = str(root / info["path"])
    return env, info
