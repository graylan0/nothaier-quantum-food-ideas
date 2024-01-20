import aiosqlite
import asyncio
import re
import numpy as np
import pennylane as qml
from textblob import TextBlob
from kivy.app import App
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.image import Image as KivyImage
import logging
import requests
import base64
import io
from PIL import Image as PILImage
import json
import os
from llama_cpp import Llama

# Load configuration from config.json
with open('config.json', 'r') as config_file:
    config = json.load(config_file)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Window.size = (360, 640)

Builder.load_string('''
<MainScreen>:
    BoxLayout:
        orientation: 'vertical'
        Button:
            text: 'Go to Settings'
            on_release: app.root.current = 'settings'
        Button:
            text: 'Generate Image'
            on_release: root.generate_image()
        Image:
            id: img
            source: ''

<SettingsScreen>:
    BoxLayout:
        orientation: 'vertical'
        TextInput:
            id: food_input
            hint_text: 'Enter Food Item'
            size_hint_y: None
            height: '48dp'
            on_text_validate: app.add_food_item(food_input.text)
        Spinner:
            id: food_spinner
            text: 'Select Food to Remove'
            size_hint_y: None
            height: '48dp'
        Button:
            text: 'Remove Selected Food'
            size_hint_y: None
            height: '48dp'
            on_release: app.remove_food_item(food_spinner.text)
        Button:
            text: 'Back to Main Screen'
            size_hint_y: None
            height: '48dp'
            on_release: app.root.current = 'main'

ScreenManager:
    MainScreen:
        name: 'main'
    SettingsScreen:
        name: 'settings'
''')


class MainScreen(Screen):
    pass

class SettingsScreen(Screen):
    pass

class HaierFridgeApp(App):
    def build(self):
        self.loop = asyncio.get_event_loop()
        self.loop.run_until_complete(self.init_db())
        self.llm = Llama(model_path=config['LLAMA_MODEL_PATH'], n_gpu_layers=-1, n_ctx=3900)
        return Builder.load_string(KV)

    async def init_db(self):
        try:
            self.db = await aiosqlite.connect(config['DB_NAME'])
            await self.db.execute("CREATE TABLE IF NOT EXISTS food (item TEXT UNIQUE)")
            await self.db.commit()
        except Exception as e:
            logger.error(f"Error initializing database: {e}")

    async def add_food_item(self, food_item):
        if food_item:
            try:
                await self.db.execute("INSERT INTO food (item) VALUES (?)", (food_item,))
                await self.db.commit()
                await self.update_food_spinner()
            except aiosqlite.IntegrityError as e:
                logger.warning(f"Food item already exists: {e}")
            except Exception as e:
                logger.error(f"Error adding food item: {e}")

    async def remove_food_item(self, food_item):
        try:
            await self.db.execute("DELETE FROM food WHERE item = ?", (food_item,))
            await self.db.commit()
            await self.update_food_spinner()
        except Exception as e:
            logger.error(f"Error removing food item: {e}")

    async def update_food_spinner(self):
        try:
            spinner = self.root.get_screen('settings').ids.food_spinner
            async with self.db.execute("SELECT item FROM food") as cursor:
                spinner.values = [row[0] for row in await cursor.fetchall()]
                spinner.text = 'Select Food to Remove' if spinner.values else ''
        except Exception as e:
            logger.error(f"Error updating food spinner: {e}")

    async def generate_color_code(self):
        try:
            async with self.db.execute("SELECT item FROM food") as cursor:
                food_items = [row[0] for row in await cursor.fetchall()]
            sentence = ', '.join(food_items)
            prompt = f"Generate a color code from the {sentence}"
            response = self.llm(prompt, max_tokens=200)
            color_code = response['choices'][0]['text'] if response['choices'] else "#FFFFFF"
            logger.info(f"Generated Color Code: {color_code}")
        except Exception as e:
            logger.error(f"Error generating color code: {e}")

    @qml.qnode(qml.device("default.qubit", wires=4))
    def quantum_circuit(self, color_code, amplitude):
        r, g, b = (int(color_code[i:i+2], 16) for i in (0, 2, 4))
        r, g, b = r / 255.0, g / 255.0, b / 255.0
        qml.RY(r * np.pi, wires=0)
        qml.RY(g * np.pi, wires=1)
        qml.RY(b * np.pi, wires=2)
        qml.RY(amplitude * np.pi, wires=3)
        qml.CNOT(wires=[0, 1])
        qml.CNOT(wires=[1, 2])
        qml.CNOT(wires=[2, 3])
        return qml.probs(wires=[0, 1, 2, 3])

    async def sentiment_to_amplitude(self, text):
        analysis = TextBlob(text)
        return (analysis.sentiment.polarity + 1) / 2

    def extract_color_code(self, response_text):
        pattern = r'#([0-9a-fA-F]{3,6})'
        match = re.search(pattern, response_text)
        if match:
            color_code = match.group(1)
            if len(color_code) == 3:
                color_code = ''.join([char*2 for char in color_code])
            return color_code
        return None

    async def save_to_database(self, color_code, quantum_state, reply, report):
        async with aiosqlite.connect('colobits.db') as db:
            async with db.cursor() as cursor:
                await cursor.execute(
                    "INSERT INTO analysis_table (color_code, quantum_state, reply, report) VALUES (?, ?, ?, ?)",
                    (color_code, quantum_state, reply, report)
                )
                await db.commit()

    def switch_screen(self, screen_name, direction):
        if direction == 'forward':
            self.root.transition.direction = 'left'
        elif direction == 'back':
            self.root.transition.direction = 'right'
        self.root.current = screen_name

    def generate_images(self, message):
        try:
            url = config['IMAGE_GENERATION_URL']
            payload = {
                "prompt": message,
                "steps": 51,
                "seed": random.randrange(sys.maxsize),
                "enable_hr": "false",
                "denoising_strength": "0.7",
                "cfg_scale": "7",
                "width": 526,
                "height": 756,
                "restore_faces": "true",
            }
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                image_data = response.json()['images']
                for img_data in image_data:
                    img_tk = self.convert_base64_to_tk(img_data)
                    # Process and display the image as needed
            else:
                logger.error(f"Error generating image: HTTP {response.status_code}")
        except Exception as e:
            logger.error(f"Error in generate_images: {e}")

    def convert_base64_to_tk(self, base64_data):
        if ',' in base64_data:
            base64_data = base64_data.split(",", 1)[1]
        image_data = base64.b64decode(base64_data)
        image = PILImage.open(io.BytesIO(image_data))
        return KivyImage(source=image)

if __name__ == '__main__':
    HaierFridgeApp().run()
