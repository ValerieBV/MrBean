from django import forms

from .models import Lesson, VocabWord, ListeningQuestion, SpeakingTask

INPUT = "w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500 text-sm"


class LessonForm(forms.ModelForm):
    class Meta:
        model = Lesson
        fields = ["skill", "program", "order", "title", "description",
                  "listening_type", "audio_file", "youtube_url", "is_active"]
        widgets = {
            "skill": forms.Select(attrs={"class": INPUT, "id": "id_skill"}),
            "program": forms.Select(attrs={"class": INPUT}),
            "order": forms.NumberInput(attrs={"class": INPUT}),
            "title": forms.TextInput(attrs={"class": INPUT}),
            "description": forms.Textarea(attrs={"class": INPUT, "rows": 2}),
            "listening_type": forms.Select(attrs={"class": INPUT}),
            "audio_file": forms.ClearableFileInput(attrs={"class": INPUT}),
            "youtube_url": forms.URLInput(attrs={"class": INPUT, "placeholder": "https://youtube.com/..."}),
        }


class VocabWordForm(forms.ModelForm):
    class Meta:
        model = VocabWord
        fields = ["order", "word", "word_type", "meaning", "example"]
        widgets = {f: forms.TextInput(attrs={"class": INPUT}) for f in ["word", "word_type", "meaning"]}
        widgets["order"] = forms.NumberInput(attrs={"class": INPUT})
        widgets["example"] = forms.Textarea(attrs={"class": INPUT, "rows": 2})


class ListeningQuestionForm(forms.ModelForm):
    class Meta:
        model = ListeningQuestion
        fields = ["order", "image", "question_text", "option_a", "option_b",
                  "option_c", "option_d", "correct_option", "correct_answer"]
        widgets = {
            "order": forms.NumberInput(attrs={"class": INPUT}),
            "image": forms.ClearableFileInput(attrs={"class": INPUT}),
            "question_text": forms.Textarea(attrs={"class": INPUT, "rows": 2}),
            "option_a": forms.TextInput(attrs={"class": INPUT}),
            "option_b": forms.TextInput(attrs={"class": INPUT}),
            "option_c": forms.TextInput(attrs={"class": INPUT}),
            "option_d": forms.TextInput(attrs={"class": INPUT}),
            "correct_option": forms.Select(attrs={"class": INPUT}),
            "correct_answer": forms.TextInput(attrs={"class": INPUT}),
        }


class SpeakingTaskForm(forms.ModelForm):
    class Meta:
        model = SpeakingTask
        fields = ["order", "sentence"]
        widgets = {
            "order": forms.NumberInput(attrs={"class": INPUT}),
            "sentence": forms.Textarea(attrs={"class": INPUT, "rows": 2}),
        }
