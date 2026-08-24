import pytest

from backend import pricing
from backend.tracers import LogTracer


@pytest.fixture
def priced(monkeypatch):
    """A fixed price list, so the tests never touch the network."""
    table = {
        "openai/gpt-5.6-luna": (0.0000002, 0.0000012, 1_000_000_000.0),
        "z-ai/glm-4.7": (0.0000004, 0.00000175, 1_000_000_000.0),
    }
    monkeypatch.setattr(pricing, "read_model_prices", lambda: table)
    monkeypatch.setattr(pricing, "_cache", None)
    monkeypatch.setattr(pricing, "_cache_read_at", 0.0)
    return table


def test_bare_name_is_an_openai_model():
    """get_model routes a name without a slash to OpenAI, so pricing must agree."""
    assert pricing.openrouter_id("gpt-5.6-luna") == "openai/gpt-5.6-luna"


def test_a_slug_is_left_alone():
    assert pricing.openrouter_id("z-ai/glm-4.7") == "z-ai/glm-4.7"


def test_cost_is_input_plus_output(priced):
    assert pricing.cost_of("z-ai/glm-4.7", 1000, 500) == pytest.approx(0.001275)


def test_bare_openai_name_is_priced(priced):
    assert pricing.cost_of("gpt-5.6-luna", 1000, 500) == pytest.approx(0.0008)


def test_unknown_model_costs_none_not_zero(priced):
    """Zero would quietly under-report the round; None lets the UI say so."""
    assert pricing.cost_of("made/up", 1000, 500) is None


@pytest.fixture
def tracer(monkeypatch, priced):
    rows = []
    monkeypatch.setattr("backend.tracers.write_usage", lambda *row: rows.append(row))
    tracer = LogTracer()
    tracer.rows = rows
    return tracer


def span(**span_data_attrs):
    data = type("SpanData", (), span_data_attrs)()
    return type("Span", (), {"span_data": data, "trace_id": "trace_warren0x", "error": None})()


def test_generation_span_is_recorded(tracer):
    tracer.record_usage("warren", span(
        type="generation", model="z-ai/glm-4.7",
        usage={"input_tokens": 1000, "output_tokens": 500},
    ))
    assert tracer.rows == [("warren", "z-ai/glm-4.7", 1000, 500, pytest.approx(0.001275))]


def test_response_span_reads_usage_one_level_down(tracer):
    """The trader on OpenAI produces response spans, not generation spans."""
    usage = type("Usage", (), {"input_tokens": 200, "output_tokens": 100})()
    response = type("Response", (), {"model": "gpt-5.6-luna", "usage": usage})()
    tracer.record_usage("warren", span(type="response", response=response))
    assert tracer.rows == [("warren", "gpt-5.6-luna", 200, 100, pytest.approx(0.00016))]


def test_span_without_usage_is_skipped(tracer):
    tracer.record_usage("warren", span(type="function", name="buy_shares"))
    assert tracer.rows == []


def test_accounting_never_breaks_a_round(tracer):
    """A malformed span must not raise out of the tracer into the round."""
    broken = type("Span", (), {"span_data": None, "trace_id": "trace_warren0x"})()
    tracer.record_usage("warren", broken)
    assert tracer.rows == []


def test_unpriced_model_still_records_tokens(tracer):
    tracer.record_usage("warren", span(
        type="generation", model="made/up",
        usage={"input_tokens": 10, "output_tokens": 5},
    ))
    assert tracer.rows == [("warren", "made/up", 10, 5, None)]
