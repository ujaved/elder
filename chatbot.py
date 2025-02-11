from pydantic import BaseModel, Field
import base64
from openai import OpenAI, pydantic_function_tool
import json
from datetime import datetime, date, time
from store import Task as CarePlanTask, Question
from utils import add_time


class TimeOfDay(BaseModel):
    hour: int = Field(
        description="Hour of the time of day. Values should be between 0 and 23."
    )
    minute: int = Field(
        description="Hour of the time of day. Values should be between 0 and 59."
    )


class Task(BaseModel):
    start_time: TimeOfDay | None = Field(description="start time of task")
    end_time: TimeOfDay | None = Field(description="end time of task")
    content: str = Field(description="content of the instruction")

    def deserialize(self) -> CarePlanTask:
        start_time = (
            time(hour=self.start_time.hour, minute=self.start_time.minute)
            if self.start_time
            else None
        )
        if self.end_time:
            end_time = time(hour=self.end_time.hour, minute=self.end_time.minute)
        elif start_time:
            end_time = add_time(start_time, 0, 30)
        else:
            end_time = None
        return CarePlanTask(
            content=self.content, start_time=start_time, end_time=end_time
        )

        """    
        start_time = parse_time(self.start_time, self.content, reference_date)
        if self.end_time:
            end_time = datetime.strptime(self.end_time, "%I:%M %p")
            end_time = end_time.replace(year=reference_date.year)
            end_time = end_time.replace(month=reference_date.month)
            end_time = end_time.replace(day=reference_date.day)
        elif start_time:
            end_time = start_time + timedelta(minutes=30)
        else:
            end_time = None
        """


class GetTasksAndQuestions(BaseModel):
    """get a list of tasks and/or a list of questions in the audio input"""

    tasks: list[Task] = Field(description="tasks found")
    questions: list[str] = Field(description="questions found")


def parse_time(
    time_str: str | None, content_str: str, reference_date: date
) -> datetime | None:
    time = None
    try:
        time = datetime.strptime(time_str, "%I:%M %p") if time_str else None
    except:
        time = datetime.strptime(time_str, "%I:%M") if time_str else None
    if time:
        time = time.replace(year=reference_date.year)
        time = time.replace(month=reference_date.month)
        time = time.replace(day=reference_date.day)
    else:
        cal = parsedatetime.Calendar()
        time_struct, parse_status = cal.parse(content_str)
        if parse_status != 0:
            time = datetime(*time_struct[:6])
    return time


def generate_tasks_from_audio(audio) -> tuple[list[CarePlanTask], list[Question]]:
    encoded_string = base64.b64encode(audio.getvalue()).decode("utf-8")
    system_prompt = """
    You are a helpful assistant. Each user input will be an audio message containing
    some instructions and questions for a health aide. An instruction might have a start time
    and/or an end time. Use the supplied function to parse the instructions and questions in their 
    respective list format. 
    """
    # The user input may also contain some existing instructions and/or questions.
    # Make usre the final output does not contain duplicates.
    completion = OpenAI().chat.completions.create(
        model="gpt-4o-audio-preview",
        modalities=["text"],
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": encoded_string, "format": "wav"},
                    },
                ],
            },
        ],
        tools=[pydantic_function_tool(GetTasksAndQuestions)],
    )
    arguments = json.loads(
        completion.choices[0].message.tool_calls[0].function.arguments
    )
    tq = GetTasksAndQuestions(**arguments)
    return (
        [task.deserialize() for task in tq.tasks],
        [Question(q, "") for q in tq.questions],
    )


def generate_answer_from_audio(audio, question: str) -> str:
    encoded_string = base64.b64encode(audio.getvalue()).decode("utf-8")
    completion = OpenAI().chat.completions.create(
        model="gpt-4o-audio-preview",
        modalities=["text"],
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant. Transcribe this audio, which is an answer to a question, also given as text.",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"The attached audio, to be transcribed, is an answer to this question {question}",
                    },
                    {
                        "type": "input_audio",
                        "input_audio": {"data": encoded_string, "format": "wav"},
                    },
                ],
            },
        ],
    )
    return completion.choices[0].message.content
