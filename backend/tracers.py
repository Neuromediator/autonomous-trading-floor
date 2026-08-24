from agents import TracingProcessor, Trace, Span
from .database import write_log, write_usage
from .pricing import cost_of
import secrets
import string

ALPHANUM = string.ascii_lowercase + string.digits 

def make_trace_id(tag: str) -> str:
    """
    Return a string of the form 'trace_<tag><random>',
    where the total length after 'trace_' is 32 chars.
    """
    tag += "0"
    pad_len = 32 - len(tag)
    random_suffix = ''.join(secrets.choice(ALPHANUM) for _ in range(pad_len))
    return f"trace_{tag}{random_suffix}"

class LogTracer(TracingProcessor):

    def get_name(self, trace_or_span: Trace | Span) -> str | None:
        trace_id = trace_or_span.trace_id
        name = trace_id.split("_")[1]
        if '0' in name:
            return name.split("0")[0]
        else:
            return None

    def on_trace_start(self, trace) -> None:
        name = self.get_name(trace)
        if name:
            write_log(name, "trace", f"Started: {trace.name}")

    def on_trace_end(self, trace) -> None:
        name = self.get_name(trace)
        if name:
            write_log(name, "trace", f"Ended: {trace.name}")

    def on_span_start(self, span) -> None:
        name = self.get_name(span)
        type = span.span_data.type if span.span_data else "span"
        if name:
            message = "Started"
            if span.span_data:
                if span.span_data.type:
                    message += f" {span.span_data.type}"
                if hasattr(span.span_data, "name") and span.span_data.name:
                    message += f" {span.span_data.name}"
                if hasattr(span.span_data, "server") and span.span_data.server:
                    message += f" {span.span_data.server}"
            if span.error:
                message += f" {span.error}"
            write_log(name, type, message)

    def on_span_end(self, span) -> None:
        name = self.get_name(span)
        type = span.span_data.type if span.span_data else "span"
        if name:
            message = "Ended"
            if span.span_data:
                if span.span_data.type:
                    
                    message += f" {span.span_data.type}"
                if hasattr(span.span_data, "name") and span.span_data.name:
                    message += f" {span.span_data.name}"
                if hasattr(span.span_data, "server") and span.span_data.server:
                    message += f" {span.span_data.server}"
            if span.error:
                message += f" {span.error}"
            write_log(name, type, message)
            self.record_usage(name, span)

    def record_usage(self, name: str, span) -> None:
        """Store the tokens a model call used, and what they cost.

        Both model paths are covered: traders on OpenRouter produce generation
        spans, and the one on OpenAI directly produces response spans, which
        carry the same numbers one level down. Anything unexpected is skipped —
        a round must not fail over accounting.
        """
        try:
            data = span.span_data
            usage = getattr(data, "usage", None)
            model = getattr(data, "model", None)
            response = getattr(data, "response", None)
            if response is not None:
                model = model or getattr(response, "model", None)
                usage = usage or getattr(response, "usage", None)
            if usage is None or not model:
                return
            if not isinstance(usage, dict):
                usage = {
                    "input_tokens": getattr(usage, "input_tokens", None),
                    "output_tokens": getattr(usage, "output_tokens", None),
                }
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
            if input_tokens is None or output_tokens is None:
                return
            write_usage(name, model, int(input_tokens), int(output_tokens),
                        cost_of(model, int(input_tokens), int(output_tokens)))
        except Exception:
            pass

    def force_flush(self) -> None:
        pass

    def shutdown(self) -> None:
        pass