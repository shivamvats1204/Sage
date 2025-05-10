# Sage: Advanced AI Chatbot Assistant

## Overview

**Sage** is an advanced AI-powered desktop assistant featuring a modern graphical user interface (GUI), real-time search, conversational AI, automation, speech-to-text, text-to-speech, and image generation capabilities. It is designed to help users interact naturally with their computer, automate tasks, retrieve up-to-date information, and generate content or images using state-of-the-art AI models.

---

## Features

- **Conversational AI**: Chat with Sage using natural language. Sage can answer questions, provide explanations, and maintain context.
- **Real-Time Search**: Fetches up-to-date information from the web using Google and YouTube search.
- **Automation**: Open/close applications, play YouTube videos, control system volume, and more.
- **Content Generation**: Write letters, emails, code, essays, and more using AI.
- **Image Generation**: Generate high-quality images from text prompts using Stable Diffusion.
- **Speech-to-Text**: Speak to Sage and have your speech transcribed and processed.
- **Text-to-Speech**: Sage can read out responses using realistic AI voices.
- **Modern GUI**: Built with PyQt5, featuring chat history, status indicators, and animated graphics.

---

## Project Structure

```
.
├── Main.py                # Main entry point
├── Requirements.txt       # Python dependencies
├── Backend/               # Backend logic and AI modules
│   ├── Model.py           # Decision-making model (Cohere)
│   ├── Chatbot.py         # Conversational AI (Groq)
│   ├── RealtimeSearchEngine.py # Real-time web search
│   ├── Automation.py      # Task automation (apps, web, system)
│   ├── ImageGeneration.py # Image generation (Stable Diffusion)
│   ├── SpeechToText.py    # Speech recognition (Selenium, Web Speech API)
│   ├── TextToSpeech.py    # Text-to-speech (edge-tts, pygame)
├── Frontend/              # GUI and user interface
│   ├── GUI.py             # PyQt5 GUI implementation
│   ├── Graphics/          # Images, GIFs for GUI
│   └── Files/             # Temporary data files (status, chat, etc.)
├── Data/                  # User data, chat logs, generated images, etc.
│   ├── ChatLog.json       # Persistent chat history
│   ├── speech.mp3         # Audio output
│   ├── *.jpg              # Generated images
│   ├── *.txt              # Generated content
│   └── Voice.html         # Speech recognition HTML
```

---

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/shivamvats1204/Sage
   cd Sage
   ```

2. **Set up a virtual environment (recommended):**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r Requirements.txt
   ```

4. **Environment Variables:**
   Create a `.env` file in the root directory with the following keys:
   ```env
   Username=YourName
   AssistantName=Sage
   CohereAPIKey=your-cohere-api-key
   GroqAPIKey=your-groq-api-key
   HuggingFaceAPIKey=your-huggingface-api-key
   AssistantVoice=en-US-JennyNeural  # or any supported voice
   InputLanguage=en
   ```

5. **Download ChromeDriver:**
   The project uses Selenium and `webdriver-manager` to auto-install ChromeDriver, but ensure you have Google Chrome installed.

---

## Usage

Run the main application:
```bash
python Main.py
```

- The GUI will launch. Use the microphone button to speak or type your queries.
- Chat history and responses are displayed in the main window.
- Sage can perform tasks, answer questions, generate images, and more.

---

## Dependencies

All dependencies are listed in `Requirements.txt`. Major libraries include:
- `PyQt5` (GUI)
- `cohere`, `groq`, `cohere` (AI models)
- `requests`, `bs4`, `selenium`, `googlesearch-python` (web search)
- `pygame`, `edge-tts` (text-to-speech)
- `pillow` (image handling)
- `python-dotenv` (environment variables)
- `pywhatkit`, `AppOpener`, `keyboard` (automation)
- `mtranslate` (translation)

---

## Data Files

- `Data/ChatLog.json`: Stores chat history.
- `Data/speech.mp3`: Stores generated speech audio.
- `Data/*.jpg`: Generated images from prompts.
- `Frontend/Files/`: Temporary files for GUI state and communication.

---

## Acknowledgements

- [Cohere](https://cohere.com/), [Groq](https://groq.com/), [HuggingFace](https://huggingface.co/) for AI APIs
- [PyQt5](https://riverbankcomputing.com/software/pyqt/intro) for GUI
- [Selenium](https://www.selenium.dev/) for speech recognition
- [edge-tts](https://github.com/ranyelhousieny/edge-tts) for TTS

---

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change. 