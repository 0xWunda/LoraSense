from abc import ABC, abstractmethod

class BaseDecoder(ABC):
    """
    Base class for all sensor decoders.
    Each sensor type must implement the decode method.
    """
    def __init__(self, payload_bytes):
        self.payload_bytes = payload_bytes

    @abstractmethod
    def decode(self):
        """Returns a dictionary of decoded values."""
        pass

class BaraniDecoder(BaseDecoder):
    """
    Decodes binary payloads from Barani MeteoHelix sensors.
    Uses bit-shifting to extract values according to the sensor's technical specification.
    """
    def __init__(self, payload_bytes):
        super().__init__(payload_bytes)
        self.pos = 0
        self.bindata = self.data2bits(payload_bytes)

    def pad(self, num):
        s = "00000000" + str(num)
        return s[-8:]

    def dec2bin(self, num):
        return self.pad(bin(num)[2:])

    def bin2dec(self, num):
        return int(num, 2)

    def data2bits(self, data):
        binary = ""
        for b in data:
            binary += self.dec2bin(b)
        return binary

    def bitShift(self, bits):
        """
        Extracts a specific number of bits from the binary data and converts to decimal.
        Updates the internal position pointer.
        """
        if self.pos + bits > len(self.bindata):
            return 0
        num = self.bin2dec(self.bindata[self.pos:self.pos+bits])
        self.pos += bits
        return num

    def precisionRound(self, number, precision):
        factor = 10 ** precision
        return round(number * factor) / factor

    def decode(self):
        """
        Main decoding loop. Extracts all sensor measurements from the bitstream.
        Constants (like 0.05 for battery or 0.1 - 100 for temperature) come from 
        the manufacturer's payload specification.
        """
        Type = self.bitShift(2)
        Battery = self.precisionRound(self.bitShift(5)*0.05 + 3, 2)
        Temperature = self.precisionRound(self.bitShift(11)*0.1 - 100, 1)
        T_min = self.precisionRound(Temperature - self.bitShift(6)*0.1, 1)
        T_max = self.precisionRound(Temperature + self.bitShift(6)*0.1, 1)
        Humidity = self.precisionRound(self.bitShift(9)*0.2, 1)
        # Pressure is offset by 50000 Pa
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
            "Pressure": Pressure / 100,  # in hPa
            "Irradiation": Irradiation,
            "Irr_max": Irr_max,
            "Rain": Rain,
            "Rain_min_time": Rain_min_time
        }

        return decoded

class ExampleSensorDecoder(BaseDecoder):
    """
    An example decoder for a simple sensor that sends temperature and humidity 
    as two bytes respectively.
    """
    def decode(self):
        if len(self.payload_bytes) < 2:
            return {"error": "Payload too short"}
        
        # Simple format: [Temp, Hum]
        temp = self.payload_bytes[0] - 40 # Offset example
        hum = self.payload_bytes[1]
        
        return {
            "Temperature": float(temp),
            "Humidity": float(hum),
            "Status": "Simple Decoded"
        }

class DecoderFactory:
    """
    Factory to manage and retrieve decoders based on configuration strings.
    """
    _decoders = {
        "v1": BaraniDecoder,
        "barani": BaraniDecoder,
        "simple": ExampleSensorDecoder
    }

    @classmethod
    def get_decoder(cls, config_str, payload_bytes):
        decoder_class = cls._decoders.get(config_str.lower(), BaraniDecoder)
        return decoder_class(payload_bytes)

def decode_payload(payload_bytes, config_str="v1"):
    """
    Facade for easy usage.
    :param payload_bytes: The raw binary data.
    :param config_str: The decoder identifier (e.g., 'v1', 'simple').
    """
    decoder = DecoderFactory.get_decoder(config_str, payload_bytes)
    return decoder.decode()
