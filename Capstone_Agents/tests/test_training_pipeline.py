import json

import pytest

from training.prepare_dataset import prepare
from training.convert_dataset_csv import convert


def _record(participant_id, index):
    return {
        "participant_id": participant_id,
        "instruction": f"Prompt {index}",
        "response": f"Answer {index}",
        "source": "locally-authored-study",
        "license": "CC-BY-4.0",
    }


def test_dataset_split_keeps_participants_disjoint_and_is_reproducible(tmp_path):
    source = tmp_path / "input.jsonl"
    source.write_text("\n".join(json.dumps(_record(f"participant-{i}", i)) for i in range(6)))
    first, second = tmp_path / "one", tmp_path / "two"
    prepare(source, first, seed=4)
    prepare(source, second, seed=4)
    groups = {}
    for split in ("train", "validation", "test"):
        records = [json.loads(line) for line in (first / f"{split}.jsonl").read_text().splitlines()]
        assert records
        groups[split] = {row["participant_id"] for row in records}
        assert (first / f"{split}.jsonl").read_bytes() == (second / f"{split}.jsonl").read_bytes()
    assert groups["train"].isdisjoint(groups["validation"])
    assert groups["train"].isdisjoint(groups["test"])
    assert groups["validation"].isdisjoint(groups["test"])


def test_dataset_rejects_missing_provenance_or_participant(tmp_path):
    source = tmp_path / "bad.jsonl"
    source.write_text(json.dumps({"instruction": "Question", "response": "Answer"}))
    with pytest.raises(ValueError, match="source, license, and participant_id"):
        prepare(source, tmp_path / "prepared")


def test_csv_conversion_rejects_email_participant_ids(tmp_path):
    source = tmp_path / "responses.csv"
    source.write_text(
        "participant_id,instruction,response,source,license\n"
        "person@example.com,Prompt,Answer,own annotation,CC-BY-4.0\n"
    )
    with pytest.raises(ValueError, match="pseudonymous participant_id"):
        convert(source, tmp_path / "out.jsonl")
