import trafilatura
url = "https://www.kartfree.com/free/kampanyadetay/8/22027/fakirde-9-taksit-mayis"
text = trafilatura.extract(trafilatura.fetch_url(url))
print(text)
