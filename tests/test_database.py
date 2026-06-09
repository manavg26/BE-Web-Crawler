from crawler.database import CrawlJobStore
from crawler.schema import CrawlRecord


def test_store_round_trips_completed_record():
    store = CrawlJobStore(":memory:")
    store.create_job("job-1", "https://example.com")
    record = CrawlRecord(
        url="https://example.com",
        final_url="https://example.com",
        http_status=200,
        title="Example Domain",
    )

    store.save_record("job-1", record)
    saved = store.get_job("job-1")

    assert saved is not None
    assert saved.status == "completed"
    assert saved.record is not None
    assert saved.record.title == "Example Domain"


def test_broker_publishes_polls_and_acks_messages():
    store = CrawlJobStore(":memory:")

    message_id = store.publish("crawl.fetch", "job-1", {"job_id": "job-1", "url": "https://example.com"})
    message = store.poll("crawl.fetch")

    assert message is not None
    assert message.message_id == message_id
    assert message.topic == "crawl.fetch"
    assert message.key == "job-1"
    assert message.payload["url"] == "https://example.com"

    store.ack(message.message_id)

    assert store.poll("crawl.fetch") is None
