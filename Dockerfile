FROM python:3.10-slim

# Crear usuario sin privilegios
RUN useradd -m -s /bin/bash appuser
WORKDIR /app

# Copiar todos los archivos del proyecto como root
COPY requirements.txt .
COPY main.py .
COPY index.html .

# Otorgar permisos totales al usuario sobre la carpeta de la aplicación
RUN chown -R appuser:appuser /app

# Cambiar al usuario sin privilegios para mayor seguridad
USER appuser

# Crear y activar un entorno virtual
ENV VIRTUAL_ENV=/home/appuser/venv
RUN python -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Instalar dependencias en el entorno virtual
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 10000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]