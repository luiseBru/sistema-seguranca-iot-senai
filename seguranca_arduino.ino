// Arduino UNO: sensor HC-SR04 + LED + buzzer.
// Envia pela USB no formato: 20.00,ALERTA ou 80.00,NORMAL
// Projeto didatico: NAO e sistema certificado de seguranca de maquinas.
const int trigPin = 9;
const int echoPin = 10;
const int ledPin = 7;
const int buzzerPin = 8;
const float limiteDistancia = 30.0; // cm

void setup() {
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  pinMode(ledPin, OUTPUT);
  pinMode(buzzerPin, OUTPUT);
  Serial.begin(9600);
}

void loop() {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  unsigned long duracao = pulseIn(echoPin, HIGH, 30000UL);

  if (duracao == 0) {
    // Sem eco: nao envie um valor de distancia falso.
    // A API indica SEM_SINAL quando para de receber leituras.
    digitalWrite(ledPin, LOW);
    noTone(buzzerPin);
  } else {
    float distancia = duracao * 0.0343 / 2.0;
    bool alerta = distancia <= limiteDistancia;

    digitalWrite(ledPin, alerta ? HIGH : LOW);
    if (alerta) {
      tone(buzzerPin, 1000);
    } else {
      noTone(buzzerPin);
    }

    Serial.print(distancia, 2);
    Serial.print(",");
    Serial.println(alerta ? "ALERTA" : "NORMAL");
  }
  delay(100);
}
