"""
Dieses Modul übernimmt die Dekodierung von rohen LoRaWAN-Payloads (Binärdaten) 
in strukturierte JSON-kompatible Dictionaries.
Es nutzt ein Factory-Muster, um verschiedene Sensortypen (z.B. Barani, Dragino) zu unterstützen.
"""

from abc import ABC, abstractmethod

class BaseDecoder(ABC):
    """
    Abstrakte Basisklasse für alle Sensor-Decoder.
    Jeder neue Sensortyp muss diese Klasse implementieren.
    """
    def __init__(self, payload_bytes):
        """
        Initialisiert den Decoder mit den Rohdaten.
        
        Args:
            payload_bytes (bytes): Die binäre Payload vom LoRaWAN-Netzwerk.
        """
        self.payload_bytes = payload_bytes

    @abstractmethod
    def decode(self):
        """
        Abstrakte Methode zur Dekodierung der Daten.
        
        Returns:
            dict: Ein Dictionary mit den extrahierten Messwerten.
        """
        pass

class BaraniDecoder(BaseDecoder):
    """
    Decoder für Barani MeteoHelix Sensoren.
    Implementiert das bitweise Parsen gemäss der technischen Spezifikation des Herstellers.
    """
    def __init__(self, payload_bytes):
        super().__init__(payload_bytes)
        self.pos = 0
        # Wandelt die Bytes in einen langen Binär-String um, um bitweise Shifting zu ermöglichen
        self.bindata = self.data2bits(payload_bytes)

    def pad(self, num):
        """Ergänzt einen Binärstring um führende Nullen auf 8 Bit."""
        s = "00000000" + str(num)
        return s[-8:]

    def dec2bin(self, num):
        """Wandelt eine Dezimalzahl in einen 8-Bit-Binärstring um."""
        return self.pad(bin(num)[2:])

    def bin2dec(self, num):
        """Wandelt einen Binärstring zurück in eine Dezimalzahl."""
        return int(num, 2)

    def data2bits(self, data):
        """Wandelt ein Byte-Array in einen kontinuierlichen Bit-String um."""
        binary = ""
        for b in data:
            binary += self.dec2bin(b)
        return binary

    def bitShift(self, bits):
        """
        Extrahiert eine bestimmte Anzahl an Bits aus dem aktuellen Bit-String und 
        verschiebt den internen Zeiger.
        
        Args:
            bits (int): Anzahl der zu lesenden Bits.
            
        Returns:
            int: Der dezimale Wert der extrahierten Bits.
        """
        if self.pos + bits > len(self.bindata):
            return 0
        num = self.bin2dec(self.bindata[self.pos:self.pos+bits])
        self.pos += bits
        return num

    def precisionRound(self, number, precision):
        """Hilfsfunktion zum kaufmännischen Runden auf eine bestimmte Nachkommastelle."""
        factor = 10 ** precision
        return round(number * factor) / factor

    def decode(self):
        """
        Haupt-Dekompressions-Logik für Barani Payloads.
        Die Faktoren (z.B. *0.05 + 3 für Batterie) stammen aus dem Payload-Dokument des Herstellers.
        """
        # Bits extrahieren (Reihenfolge ist fix gemäss Spezifikation)
        Type = self.bitShift(2)
        Battery = self.precisionRound(self.bitShift(5)*0.05 + 3, 2)
        Temperature = self.precisionRound(self.bitShift(11)*0.1 - 100, 1)
        T_min = self.precisionRound(Temperature - self.bitShift(6)*0.1, 1)
        T_max = self.precisionRound(Temperature + self.bitShift(6)*0.1, 1)
        Humidity = self.precisionRound(self.bitShift(9)*0.2, 1)
        # Luftdruck ist in der Payload um 500 hPa versetzt gespeichert
        Pressure = self.bitShift(14)*5 + 50000
        Irradiation = self.bitShift(10)*2
        Irr_max = Irradiation + self.bitShift(9)*2
        Rain = self.precisionRound(self.bitShift(8), 1)
        Rain_min_time = self.precisionRound(self.bitShift(8), 1)

        decoded = {
            "Type": Type,
            "Battery": Battery,
            "Temperature": Temperature,
            "T_min": T_min,
            "T_max": T_max,
            "Humidity": Humidity,
            "Pressure": Pressure / 100,  # Konvertierung in hPa
            "Irradiation": Irradiation,
            "Irr_max": Irr_max,
            "Rain": Rain,
            "Rain_min_time": Rain_min_time
        }

        return decoded

class ExampleSensorDecoder(BaseDecoder):
    """
    Ein Beispiel-Decoder für einen einfachen Sensor, der Temperatur (Byte 0) 
    und Luftfeuchtigkeit (Byte 1) sendet.
    """
    def decode(self):
        if len(self.payload_bytes) < 2:
            return {"error": "Payload zu kurz"}
        
        # Einfaches Format: Byte 0 - 40 (Offset) = Temperatur, Byte 1 = Feuchte
        temp = self.payload_bytes[0] - 40
        hum = self.payload_bytes[1]
        
        return {
            "Temperature": float(temp),
            "Humidity": float(hum),
            "Status": "Einfach dekodiert"
        }

class DecoderFactory:
    """
    Factory-Klasse, die anhand eines Konfigurations-Strings den passenden Decoder auswählt.
    """
    _decoders = {
        "v1": BaraniDecoder,
        "barani": BaraniDecoder,
        "simple": ExampleSensorDecoder
    }

    @classmethod
    def get_decoder(cls, config_str, payload_bytes):
        """
        Gibt eine Instanz des passenden Decoders zurück. Standard ist Barani.
        
        Args:
            config_str (str): Der Name des Decoders (z.B. 'v1').
            payload_bytes (bytes): Die zu dekodierenden Daten.
        """
        decoder_class = cls._decoders.get(config_str.lower(), BaraniDecoder)
        return decoder_class(payload_bytes)

def decode_payload(payload_bytes, config_str="v1"):
    """
    Bequeme Hilfsfunktion zum Dekodieren einer Payload ohne manuelles Factory-Handling.
    
    Args:
        payload_bytes (bytes): Die binären Rohdaten.
        config_str (str): Der Bezeichner des Sensortyps / Decoders.
        
    Returns:
        dict: Die dekodierten Messwerte.
    """
    decoder = DecoderFactory.get_decoder(config_str, payload_bytes)
    return decoder.decode()
