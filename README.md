# Sentinela IoT — Arduino + Raspberry Pi + MQTT + FastAPI

Sistema didático de monitoramento de distância para máquinas. O Arduino aciona o
alarme local, o Raspberry Pi recebe as leituras pela USB, publica por MQTT, salva
o histórico em SQLite e disponibiliza um painel web em tempo real.

> Este projeto é educacional e não substitui relés, sensores, CLPs ou outros
> componentes certificados para segurança de máquinas.

## O que está incluído

- leitura do HC-SR04 com Arduino Uno;
- LED e buzzer acionados localmente a até 30 cm;
- ponte USB serial para MQTT com reconexão automática;
- broker Mosquitto restrito ao próprio Raspberry Pi;
- API FastAPI com documentação automática;
- banco SQLite para leituras e ocorrências;
- painel web responsivo, sem dependências externas;
- atualização ao vivo por WebSocket;
- histórico em gráfico e reconhecimento de alertas;
- modo de simulação para testar sem Arduino;
- serviços `systemd` e instalador para Raspberry Pi.

## Arquitetura

```text
HC-SR04 → Arduino → USB serial → serial_para_mqtt.py → Mosquitto
                                                            │
                                                            ▼
                         navegador ← FastAPI/WebSocket ← SQLite
```

O Arduino envia uma linha no formato:

```text
20.00,ALERTA
80.00,NORMAL
```

O publicador transforma essa linha em JSON e envia ao tópico
`seguranca/maquina1/status`. A API mantém o estado atual em memória e grava uma
amostra por segundo no banco, além de toda mudança entre `NORMAL` e `ALERTA`.

## Instalação automática no Raspberry Pi

No terminal do Raspberry Pi, entre na pasta do projeto e execute:

```bash
chmod +x deploy/install_raspberry.sh
bash deploy/install_raspberry.sh
```

O instalador:

1. instala Mosquitto e Python;
2. cria o ambiente virtual e instala as bibliotecas;
3. adiciona o usuário ao grupo `dialout`;
4. configura o broker somente em `127.0.0.1`;
5. instala e inicia a API e o publicador como serviços.

Ao terminar, abra no notebook ou celular conectado à mesma rede:

```text
http://IP_DO_RASPBERRY:8000
```

Para descobrir o IP:

```bash
hostname -I
```

Se o Arduino estiver em outra porta, descubra a porta e edite a configuração:

```bash
.venv/bin/python -m serial.tools.list_ports -v
sudo nano /etc/default/seguranca-iot
sudo systemctl restart seguranca-publicador
```

As portas mais comuns são `/dev/ttyACM0` e `/dev/ttyUSB0`. Depois da primeira
instalação, encerre a sessão do Raspberry e entre novamente para garantir que o
grupo `dialout` foi aplicado ao usuário.

## Montagem do Arduino

Os pinos definidos em `seguranca_arduino.ino` são:

| Componente | Pino Arduino |
|---|---:|
| HC-SR04 TRIG | D9 |
| HC-SR04 ECHO | D10 |
| LED com resistor | D7 |
| Buzzer | D8 |

Carregue `seguranca_arduino.ino` pela Arduino IDE. Abra o Monitor Serial em
9600 baud e confirme as linhas no formato esperado. Feche o Monitor Serial antes
de iniciar o publicador no Raspberry, pois somente um programa pode usar a porta.

## Teste rápido sem Arduino

É possível testar o sistema inteiro usando dados simulados.

No Linux ou Raspberry Pi:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
SIMULAR=1 python serial_para_mqtt.py
```

Em outro terminal:

```bash
source .venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

No Windows PowerShell, a variável do simulador é definida assim:

```powershell
$env:SIMULAR = "1"
python serial_para_mqtt.py
```

O Mosquitto precisa estar ativo em `127.0.0.1:1883`.

## API

| Método | Caminho | Uso |
|---|---|---|
| GET | `/` | painel web |
| GET | `/api/status` | estado atual |
| GET | `/api/readings?limit=120` | histórico de leituras |
| GET | `/api/alerts?limit=50` | ocorrências recentes |
| POST | `/api/alerts/{id}/acknowledge` | reconhecer ocorrência |
| GET | `/health/live` | processo da API ativo |
| GET | `/health/ready` | MQTT e banco disponíveis |
| WS | `/ws/status` | estado em tempo real |
| GET | `/docs` | documentação interativa |

O endpoint de reconhecimento recebe:

```json
{"operator": "nome do operador"}
```

## Banco de dados

O banco é criado automaticamente em `data/seguranca.db`. Ele contém:

- `readings`: histórico de distância, situação, origem e horário;
- `alerts`: início, término, menor distância e reconhecimento das ocorrências.

Para fazer backup com os serviços parados:

```bash
sudo systemctl stop seguranca-api
cp data/seguranca.db data/seguranca-backup.db
sudo systemctl start seguranca-api
```

## Configuração

No Raspberry, as variáveis ficam em `/etc/default/seguranca-iot`:

```text
MQTT_HOST=127.0.0.1
MQTT_PORT=1883
DEVICE_ID=maquina1
PORTA_ARDUINO=/dev/ttyACM0
DATABASE_PATH=/caminho/do/projeto/data/seguranca.db
PERSIST_INTERVAL_SECONDS=1
STALE_AFTER_SECONDS=5
SIMULAR=0
```

Após editar esse arquivo:

```bash
sudo systemctl restart seguranca-api seguranca-publicador
```

## Diagnóstico no Raspberry Pi

```bash
sudo systemctl status mosquitto seguranca-api seguranca-publicador
sudo journalctl -u seguranca-api -f
sudo journalctl -u seguranca-publicador -f
mosquitto_sub -h 127.0.0.1 -t 'seguranca/#' -v
```

Quando nenhuma leitura chega por mais de cinco segundos, o painel apresenta
`SEM SINAL`. Se o broker for reiniciado, os dois programas tentam se reconectar
automaticamente.

## Testes automatizados

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Os testes cobrem o parser serial, mensagens MQTT, banco, ciclo de alertas e os
principais endpoints da API.

## Segurança

O Mosquitto é configurado para aceitar conexões somente no próprio Raspberry.
A página fica disponível na rede local pela porta 8000. Não encaminhe essa porta
diretamente para a internet. Para acesso remoto seriam necessários HTTPS,
autenticação e regras adicionais de rede.

O alarme local continua funcionando sem MQTT ou FastAPI. Ainda assim, uma
aplicação industrial deve usar circuito de parada e componentes certificados e
deve definir um comportamento seguro para falha ou ausência de eco do sensor.
