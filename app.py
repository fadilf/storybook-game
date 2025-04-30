import io
import json
import random
from enum import Enum
import pickle
import streamlit as st
from google import genai
import fal_client
from dotenv import load_dotenv, dotenv_values

load_dotenv()

def on_queue_update(update):
    if isinstance(update, fal_client.InProgress):
        for log in update.logs:
            print(log["message"])


client = genai.Client(api_key=dotenv_values()["GEMINI_API_KEY"])

if "stage" not in st.session_state:
    st.session_state["stage"] = 1

    # st.session_state["stage"] = 3
    # # Load the game data from the pickle file
    # with open("game_data.pkl", "rb") as f:
    #     data = pickle.load(f)
    # st.session_state["syllabus"] = data["syllabus"]
    # st.session_state["characters"] = data["characters"]
    # st.session_state["scenes"] = data["scenes"]

    # syllabus = st.session_state["syllabus"]
    # characters = st.session_state["characters"]
    # scenes = st.session_state["scenes"]

    # # Initialize the game variables
    # st.session_state["question"] = 0
    # st.session_state["level"] = 0
    # st.session_state["chat"] = [
    #     (characters[0]['Character Name'], scenes[0]['questions'][0])
    # ]


if st.session_state["stage"] == 1:
    st.write("Set up your adventure")
    uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")
    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        st.session_state["pdf"] = file_bytes
        theme = st.text_input("Enter a theme", value="medieval", placeholder="Medieval, Sci-Fi, etc.")
        if theme:
            st.session_state["theme"] = theme
            st.button(
                "Continue", on_click=lambda: st.session_state.update({"stage": 2})
            )

elif st.session_state["stage"] == 2:
    st.write("Loading your adventure...")
    st.write("This may take a few minutes, please be patient.")
    # Generate syllabus
    source_pdf = client.files.upload(file=io.BytesIO(st.session_state["pdf"]), config={"mime_type":"application/pdf"})
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[
            """Pretend you are an educator. Create a syllabus based on the attached document that teaches its contents through a set of 5 lessons with 5 true or false questions per lessons.

Provide your reponse in the following JSON format. Ensure that the formatting is correct and that the JSON is valid:
[
    {
        "lesson": "Title of first lesson",
        "questions": [
            {
                "Q": "Question 1",
                "A": true
            },
            {
                "Q": "Question 2",
                "A": false
            },
            ...
        ]
    }...
]""",
            source_pdf,
        ],
    )
    syllabus = json.loads(response.text[8:-4])

    # Generate characters
    lessons = "\n".join(["- " + lesson["lesson"] for lesson in syllabus])
    character_prompt = r"""Pretend you are a game designer. Create a set of characters - one for each of the lessons listed below - that collectively form a story progression for the player.

Lessons:
""" + lessons + r"""

The characters will quiz the player on their respective lessons and after successfully passing each character, the player experiences story events that lead them to the next character until they complete the game. The characters must be themed around the """ + st.session_state["theme"] + r""" era.

Provide your response in the following JSON formatting. Ensure that the formatting is correct and that the JSON is valid. Do not include any other text or explanation in your response:
[
    {
        'Character Name': 'Name of character',
        'Description': 'Description of character',
        'Post Completion': 'Story events that happen after successfully finishing the character interactions'
    },
    ...
]"""
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[character_prompt],
    )
    characters = json.loads(response.text[8:-4])

    # Generate dialogue trees
    scenes = []
    for character in range(len(characters)):
        questions = "\n".join(["- " + item["Q"] for item in syllabus[character]["questions"]])
        name = characters[character]['Character Name']
        desc = characters[character]['Description']
        scene_prompt = f"""Pretend you are a game master introducing a scene to a player where they interact with the following character:
    Name: {name}
    Description: {desc}

    Generate a dialog path for the character to ask the player the following true or false questions
    {questions}""" + r"""

    Provide the dialog tree in the following JSON format. Ensure that the formatting is correct and that the JSON is valid:
    {
        "scene introduction": <How the game master would introduce the scene>,
        "image prompt": <A prompt for an image generation model to create an image of the scene from the player's POV>,
        "questions": [
            <Question 1 as the character would ask it without changing any key terminology>,
            ...
        ],
        "correct responses": [
            <Ways in which the character would say the player has responded correctly>
        ],
        "incorrect responses": [
            <Ways in which the character would say the player has responded incorrectly>
        ]
    }"""
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[scene_prompt],
        )
        scene = json.loads(response.text[8:-4])
        result = fal_client.subscribe(
            "fal-ai/flux/schnell",
            arguments={
                "prompt": scene["image prompt"]
            },
            with_logs=True,
            on_queue_update=on_queue_update,
        )
        scene["image"]  = result["images"][0]["url"]
        scenes.append(scene)
    st.session_state["syllabus"] = syllabus
    st.session_state["characters"] = characters
    st.session_state["scenes"] = scenes

    st.session_state["question"] = 0
    st.session_state["level"] = 0
    st.session_state["chat"] = [
        (characters[0]['Character Name'], scenes[0]['questions'][0])
    ]

    st.write("Your adventure is ready!")
    st.button("Start", on_click=lambda: st.session_state.update({"stage": 3}))

elif st.session_state["stage"] == 3:
    syllabus = st.session_state["syllabus"]
    characters = st.session_state["characters"]
    scenes = st.session_state["scenes"]

    level = st.session_state["level"]
    scene = scenes[level]
    lesson = syllabus[level]
    character = characters[level]
    name = character["Character Name"]

    answer = lesson["questions"][st.session_state["question"]]["A"]

    col1, col2 = st.columns(2)
    with col1:
        st.write(scene["scene introduction"])
        st.image(scene["image"])

    with col2:
        chat_container = st.container(height=500)
        with chat_container:
            for msg in st.session_state["chat"]:
                st.chat_message(msg[0]).write(msg[1])

        btn_container = st.container().empty()
        with btn_container:
            b1, b2 = st.columns(2)
        with b1:
            true_btn = st.button("True", use_container_width=True)
        with b2:
            false_btn = st.button("False", use_container_width=True)
        
        if true_btn or false_btn:
            if (true_btn, false_btn) == (answer, not answer):
                new_msg = random.choice(scenes[level]['correct responses'])
            else:
                new_msg = random.choice(scenes[level]['incorrect responses'])

            submission = "True" if true_btn else "False"
            st.session_state["chat"].extend([
                ("user", submission),
                (name, new_msg)
            ])
            chat_container.chat_message("user").write(submission)
            chat_container.chat_message(name).write(new_msg)

            if (true_btn, false_btn) == (answer, not answer):
                st.session_state["question"] += 1
                if st.session_state["question"] == len(lesson["questions"]):
                    if level < len(syllabus) - 1:
                        st.session_state["question"] = 0
                        st.session_state["chat"] = [
                            (characters[level + 1]['Character Name'], scenes[level + 1]['questions'][0])
                        ]
                        chat_container.write(character['Post Completion'])
                        with btn_container:
                            st.button("Continue", on_click=lambda: st.session_state.update({"level": level + 1}), use_container_width=True)
                    else:
                        with btn_container:
                            st.button("Continue", on_click=lambda: st.session_state.update({"stage": 4}), use_container_width=True)

                else:
                    new_q = scene['questions'][st.session_state["question"]]
                    st.session_state["chat"].append(
                        (name, new_q)
                    )
                    chat_container.chat_message(name).write(new_q)

elif st.session_state["stage"] == 4:
    st.write(st.session_state['characters'][-1]['Post Completion'])
    st.write("Confgratulations! You have completed the game.")