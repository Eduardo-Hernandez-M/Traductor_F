FROM python:3.10-slim

RUN useradd -m -s /bin/bash appuser
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Descarga previa de los modelos para evitar timeouts en el primer arranque
RUN python -c "from transformers import pipeline; pipeline('translation', model='Helsinki-NLP/opus-mt-es-zh'); pipeline('translation', model='Helsinki-NLP/opus-mt-zh-es')"

COPY main.py .

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 10000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]