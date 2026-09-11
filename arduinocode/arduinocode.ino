#define TRIG1 2
#define ECHO1 3

#define TRIG2 4
#define ECHO2 5

#define GREEN1 6
#define RED1 7

#define GREEN2 8
#define RED2 9

#define BUZZER 10

#define CAR_DISTANCE 10


long readDistance(int trigPin, int echoPin)
{
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);

  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);

  digitalWrite(trigPin, LOW);

  long duration = pulseIn(echoPin, HIGH, 30000);

  if (duration == 0)
    return -1;

  return duration * 0.0343 / 2;
}


void setup()
{
  Serial.begin(9600);

  pinMode(TRIG1, OUTPUT);
  pinMode(ECHO1, INPUT);

  pinMode(TRIG2, OUTPUT);
  pinMode(ECHO2, INPUT);

  pinMode(GREEN1, OUTPUT);
  pinMode(RED1, OUTPUT);

  pinMode(GREEN2, OUTPUT);
  pinMode(RED2, OUTPUT);

  pinMode(BUZZER, OUTPUT);

  digitalWrite(BUZZER, LOW);
}


void loop()
{
  long distance1 = readDistance(TRIG1, ECHO1);

  delay(100);

  long distance2 = readDistance(TRIG2, ECHO2);


  bool slot1Occupied =
      (distance1 > 0 && distance1 < CAR_DISTANCE);

  bool slot2Occupied =
      (distance2 > 0 && distance2 < CAR_DISTANCE);


  // SLOT 1 LEDs
  if (slot1Occupied)
  {
    digitalWrite(RED1, HIGH);
    digitalWrite(GREEN1, LOW);
  }
  else
  {
    digitalWrite(RED1, LOW);
    digitalWrite(GREEN1, HIGH);
  }


  // SLOT 2 LEDs
  if (slot2Occupied)
  {
    digitalWrite(RED2, HIGH);
    digitalWrite(GREEN2, LOW);
  }
  else
  {
    digitalWrite(RED2, LOW);
    digitalWrite(GREEN2, HIGH);
  }


  // BUZZER
  if (slot1Occupied && slot2Occupied)
  {
    tone(BUZZER, HIGH);
  }
  else
  {
    noTone(BUZZER);
  }


  // SEND DATA TO LAPTOP
  Serial.print("SLOT1:");
  Serial.print(slot1Occupied ? "OCCUPIED" : "EMPTY");

  Serial.print(",SLOT2:");
  Serial.println(slot2Occupied ? "OCCUPIED" : "EMPTY");


  delay(500);
}