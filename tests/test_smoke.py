import wave
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "en_15s.wav"


def test_backend_imports_and_fixture_is_15_seconds() -> None:
    import backend

    assert backend.__name__ == "backend"
    with wave.open(str(FIXTURE), "rb") as wav:
        seconds = wav.getnframes() / wav.getframerate()
        assert wav.getframerate() == 16000
        assert wav.getnchannels() == 1
    assert 14 <= seconds <= 16
