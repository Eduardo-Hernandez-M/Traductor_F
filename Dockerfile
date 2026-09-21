FROM python:3.10-slim

# Crear usuario sin privilegios
RUN useradd -m -s /bin/bash appuser
WORKDIR /app

# Cambiar al usuario sin privilegios antes de instalar paquetes
USER appuser

# Crear y activar un entorno virtual
ENV VIRTUAL_ENV=/home/appuser/venv
RUN python -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Copiar archivos e instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código fuente y la página web
COPY main.py .
COPY index.html .

EXPOSE 10000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]