from django import forms

from .models import Enquiry


class EnquiryForm(forms.ModelForm):
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))  # honeypot

    class Meta:
        model = Enquiry
        fields = ("name", "phone", "email", "interested_in", "message")
        labels = {"interested_in": "I’m interested in"}
        widgets = {"message": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        for n, f in self.fields.items():
            if n != "website":
                f.widget.attrs.setdefault("class", "field-input")

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("Spam detected.")
        return ""

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.status = Enquiry.Status.NEW
        if commit:
            obj.save()
        return obj
