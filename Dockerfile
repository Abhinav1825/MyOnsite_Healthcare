FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY static/ ./static/
COPY run.py .

EXPOSE 5000

# gunicorn, not the Flask dev server: multiple worker processes so the app
# can actually handle concurrent load (the dev server used by `python
# run.py` is single-threaded and only intended for local development).
CMD ["gunicorn", "-w", "4", "--threads", "4", "-b", "0.0.0.0:5000", "run:app"]
