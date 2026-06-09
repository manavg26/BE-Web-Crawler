from crawler.classifier import classify_page_type, extract_topics
from crawler.parser import parse_html


HTML = """
<!doctype html>
<html lang="en">
  <head>
    <title>Best Trail Running Shoes</title>
    <meta name="description" content="A field guide to choosing trail running shoes.">
    <meta name="keywords" content="running, shoes, trails">
    <meta property="og:title" content="Trail Running Shoes Guide">
    <link rel="canonical" href="https://example.com/blog/trail-running-shoes">
    <script type="application/ld+json">
      {"@context":"https://schema.org","@type":"Article","headline":"Best Trail Running Shoes"}
    </script>
  </head>
  <body>
    <h1>Best Trail Running Shoes</h1>
    <h2>Grip and Comfort</h2>
    <article>
      Trail running shoes need durable grip, comfort, protection, and stable fit.
      Trail runners should compare grip, comfort, terrain, and weather.
    </article>
  </body>
</html>
"""


def test_parse_html_extracts_unified_fields():
    parsed = parse_html(HTML)

    assert parsed["title"] == "Best Trail Running Shoes"
    assert parsed["meta_description"] == "A field guide to choosing trail running shoes."
    assert parsed["meta_keywords"] == ["running", "shoes", "trails"]
    assert parsed["canonical"] == "https://example.com/blog/trail-running-shoes"
    assert parsed["headings"].h1 == ["Best Trail Running Shoes"]
    assert "Article" in parsed["structured_data"].types
    assert "Trail running shoes" in parsed["body_text"]


def test_classifier_uses_schema_and_url_signals():
    parsed = parse_html(HTML)

    page_type = classify_page_type(
        "https://example.com/blog/trail-running-shoes",
        parsed["structured_data"],
        parsed["title"],
        parsed["headings"].h1,
    )

    assert page_type == "article"


def test_topic_extraction_returns_ranked_topics():
    topics = extract_topics([
        "Best Trail Running Shoes",
        "Trail running shoes with grip and comfort",
        "Trail grip comfort grip comfort",
    ])

    assert topics[0].label in {"trail", "grip", "comfort", "running", "shoes"}
    assert 0 <= topics[0].score <= 1
