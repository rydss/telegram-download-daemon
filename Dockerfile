FROM python:3
RUN git clone https://github.com/rydss/telegram-download-daemon.git
RUN pip install -r /telegram-download-daemon/requirements.txt
CMD python3 /telegram-download-daemon/telegram-download-daemon.py
