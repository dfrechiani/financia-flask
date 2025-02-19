# Use uma imagem base Python
FROM python:3.9-slim

# Cria o diretório de trabalho
WORKDIR /app

# Copia o arquivo de dependências e instala
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código do app
COPY app.py .

# Define a variável de ambiente para a porta (Cloud Run usa 8080)
ENV PORT 8080

# Instala o Gunicorn (servidor para produção)
RUN pip install gunicorn

# Comando para iniciar o servidor via Gunicorn
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app
