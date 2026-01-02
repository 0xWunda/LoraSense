CREATE DATABASE IF NOT EXISTS lorasense;
USE lorasense;

CREATE TABLE IF NOT EXISTS measurements (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp DATETIME NOT NULL,
    type INT,
    battery FLOAT,
    temperature FLOAT,
    t_min FLOAT,
    t_max FLOAT,
    humidity FLOAT,
    pressure FLOAT,
    irradiation FLOAT,
    irr_max FLOAT,
    rain FLOAT,
    rain_min_time FLOAT,
    raw_data TEXT
);
