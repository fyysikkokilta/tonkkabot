# Tonkkabot

Tonkkabot is a Telegram bot that tracks the temperature at Helsinki-Vantaa (EFHK) airport and helps you know when it's time for "tönkkä" (wine-drinking weather) - when the temperature reaches 20°C or above.

## Features

- **Current Temperature**: Get the current temperature at Helsinki-Vantaa airport
- **Temperature History**: View temperature graphs for the last 2-24 hours
- **Weather Forecast**: See temperature forecasts for the next 2-48 hours
- **Tönkkä Alert**: Automatically tracks when the temperature first reaches 20°C each year
- **Beautiful Plots**: High-quality temperature graphs with the 20°C threshold marked

## Commands

- `/start` - Get information about the bot
- `/temperature` - Get current temperature
- `/history [hours]` - Get temperature history (default: 24 hours, max: 24 hours)
- `/forecast [hours]` - Get temperature forecast (default: 48 hours, max: 48 hours)

## Installation

### Prerequisites

- Python 3.13 or higher
- Telegram Bot Token (get from [@BotFather](https://t.me/botfather))

### Setup

1. Clone the repository:

```bash
git clone <repository-url>
cd Tonkkabot
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set up environment variables:

```bash
# Copy the example environment file
cp bot.env.example bot.env

# Edit bot.env and add your Telegram bot token
echo "BOT_TOKEN=your_bot_token_here" > bot.env
```

4. Run the bot:

```bash
python tonkkabot.py
```

### Docker Setup

1. Build the Docker image:

```bash
docker build -t tonkkabot .
```

2. Run the container:

```bash
docker run --env-file bot.env tonkkabot
```

## Data Sources

The bot fetches weather data from the Finnish Meteorological Institute (FMI) Open Data API:

- **Historical data**: FMI observations API
- **Forecast data**: FMI Harmonie forecast model

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is licensed under the MIT License - see the LICENSE file for details.
