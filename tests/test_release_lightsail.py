from datetime import datetime, timezone

from scripts.release_lightsail import collect_log_events


class FakeLightsail:
    def __init__(self):
        self.calls = []

    def get_container_log(self, **kwargs):
        self.calls.append(kwargs)
        if "pageToken" not in kwargs:
            return {
                "logEvents": [
                    {
                        "createdAt": datetime(2026, 9, 10, 21, 2, tzinfo=timezone.utc),
                        "message": "second",
                    }
                ],
                "nextPageToken": "page-2",
            }
        return {
            "logEvents": [
                {
                    "createdAt": datetime(2026, 9, 10, 21, 1, tzinfo=timezone.utc),
                    "message": "first",
                }
            ],
            # Lightsail may repeat the terminal token instead of omitting it.
            "nextPageToken": "page-2",
        }


def test_collect_log_events_reads_every_page_and_orders_events():
    lightsail = FakeLightsail()
    start = datetime(2026, 9, 10, 21, 0, tzinfo=timezone.utc)
    end = datetime(2026, 9, 10, 21, 3, tzinfo=timezone.utc)

    events = collect_log_events(lightsail, start_time=start, end_time=end)

    assert [event["message"] for event in events] == ["first", "second"]
    assert len(lightsail.calls) == 2
    assert lightsail.calls[0]["startTime"] == start
    assert lightsail.calls[0]["endTime"] == end
    assert lightsail.calls[1]["pageToken"] == "page-2"
