# Sistema de segurança — Arduino + Raspberry Pi + MQTT + FastAPI

## Arquitetura

1. O **Arduino** mede com HC-SR04 e aciona LED/buzzer localmente.
2. O Arduino envia `20.00,ALERTA` por **USB serial**, 9600 baud.
3. O programa **serial_para_mqtt.py** lê a serial e **publica** JSON no tópico MQTT `seguranca/maquina1/status`.
4. O **Mosquitto**, no Raspberry Pi, é o broker que entrega as mensagens.
5. O **main.py** do FastAPI **assina** o tópico MQTT e oferece `GET /status` e `GET /docs`.

**Atenção:** esta é uma demonstração acadêmica, não proteção certificada para máquinas. O alarme local do Arduino funciona sem a rede; no exemplo, a ausência de eco desliga o LED/buzzer e interrompe a publicação de leituras. Um equipamento industrial precisaria ter medidas adequadas de segurança e falha segura.

## A) Arduino físico

1. Faça a montagem física seguindo os pinos existentes no código: TRIG D9, ECHO D10, LED D7 (resistor em série), buzzer D8, GND e alimentação adequados.
2. No Arduino IDE, abra `seguranca_arduino.ino` (ou, no código atual, troque somente os `Serial.print` para enviar `distancia,ALERTA` ou `distancia,NORMAL`).
3. Faça **Carregar** para a placa física, teste LED, buzzer e Monitor Serial em 9600 baud; confirme linhas como `20.00,ALERTA`. Feche o Monitor Serial.
4. Conecte o Arduino por **USB de dados** ao Raspberry Pi.

## B) Acessar o terminal do Raspberry Pi

- Com tela, teclado e mouse conectados ao Pi, abra o aplicativo Terminal.
- Sem tela, use **SSH** desde que o Raspberry Pi OS e o SSH já estejam configurados e o Pi esteja na mesma rede: `ssh usuario@raspberrypi.local`. Substitua `usuario` pelo usuário criado na instalação. Se ainda nao houver SO/SSH, configure o microSD pelo Raspberry Pi Imager no notebook; a placa precisa ser inicializada com o cartão.
- Não é necessário remover o cartão microSD para programar, quando o sistema já estiver configurado.

## C) Instalar Mosquitto no Raspberry Pi

```bash
sudo apt update
sudo apt install -y mosquitto mosquitto-clients python3-venv
sudo systemctl enable --now mosquitto
sudo systemctl status mosquitto --no-pager
```

Para testar o broker, em **um terminal**:

```bash
mosquitto_sub -h 127.0.0.1 -t teste/seguranca
```

E em **outro terminal**:

```bash
mosquitto_pub -h 127.0.0.1 -t teste/seguranca -m "MQTT funcionando"
```

O primeiro terminal deve mostrar `MQTT funcionando`. Use Ctrl+C para encerrar esse teste. O broker fica configurado para acesso local no Raspberry, não precisa abrir a porta 1883 para toda a rede.

## D) Copiar projeto e instalar bibliotecas Python no Raspberry

Copie a **pasta inteira deste projeto** para a home do Pi e execute:

```bash
cd ~/seguranca_mqtt_raspberry
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m serial.tools.list_ports -v
```

Identifique a porta do Arduino: geralmente `/dev/ttyACM0` ou `/dev/ttyUSB0`. Em caso de `Permission denied`: `sudo usermod -aG dialout "$USER"`, depois encerre a sessão e entre novamente.

## E) Executar os dois programas

Com o Mosquitto ativo, abra **dois terminais do Raspberry Pi**.

Terminal 1 — USB do Arduino -> MQTT:

```bash
cd ~/seguranca_mqtt_raspberry
source .venv/bin/activate
PORTA_ARDUINO=/dev/ttyACM0 python serial_para_mqtt.py
```

Troque `/dev/ttyACM0` pela sua porta identificada, se necessário.

Terminal 2 — MQTT -> FastAPI:

```bash
cd ~/seguranca_mqtt_raspberry
source .venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

**Não use `--reload` com o hardware físico**. Não abra outro leitor da mesma porta serial, como o Monitor Serial do Arduino IDE.

No navegador do Pi: `http://127.0.0.1:8000/docs`, depois GET `/status` -> Try it out -> Execute.

Para abrir no notebook na **mesma rede**, obtenha o IP do Pi pelo comando `hostname -I` e visite `http://IP_DO_PI:8000/docs`.

Teste adicional em terceiro terminal (para enxergar as mensagens publicadas):

```bash
mosquitto_sub -h 127.0.0.1 -t seguranca/maquina1/status -v
```

Se a API mostrar `SEM_SINAL`, veja se o publicador está rodando, se o broker está ativo e se o sensor Arduino envia linhas no formato correto.

## F) Testar sem placa física (opcional)

Com Mosquitto instalado e ativo, rode no terminal 1:

```bash
cd ~/seguranca_mqtt_raspberry
source .venv/bin/activate
SIMULAR=1 python serial_para_mqtt.py
```

O terminal 2 continua igual, iniciando o FastAPI. Para sair, use Ctrl+C.

## Segurança de rede

O Mosquitto usa `127.0.0.1` para seus clientes neste projeto; não abra a porta MQTT para a rede nem configure acesso anônimo remoto. A API HTTP fica disponível na rede local quando iniciada com `--host 0.0.0.0`, então use-a apenas em rede confiável. Para internet, precisa de autenticação, autorização e TLS.
