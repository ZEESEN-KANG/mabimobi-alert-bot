FROM python:3.11-slim

ENV TZ=Asia/Seoul

# 타임존 데이터 설치 및 설정
RUN apt-get update && \
    apt-get install -y tzdata && \
    ln -sf /usr/share/zoneinfo/Asia/Seoul /etc/localtime && \
    echo "Asia/Seoul" > /etc/timezone && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt
COPY . .

CMD ["python", "main.py"]
