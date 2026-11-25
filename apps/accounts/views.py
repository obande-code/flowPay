from django import forms
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import redirect, render

from apps.audit.services import audit
from apps.payments.models import Payment

from .models import Account, User


class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].help_text = (
            'Required. 8 characters or more, 150 characters or fewer. '
            'Letters, digits and @/./+/-/_ only.'
        )

    def clean_username(self):
        username = self.cleaned_data['username']
        if len(username) < 8:
            raise forms.ValidationError('Username must be 8 characters or more.')
        return username


def signup(request):
    if request.user.is_authenticated:
        return redirect('businesses:register')

    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            Account.objects.create(user=user)
            audit('user.signed_up', username=user.username)
            login(request, user)
            return redirect('businesses:register')
    else:
        form = SignupForm()

    return render(request, 'accounts/signup.html', {'form': form})


@login_required
def users_list(request):
    users = User.objects.order_by('username')
    businesses = request.user.businesses.all()
    payments = (
        Payment.objects.filter(business__owner=request.user)
        .select_related('business')
        .order_by('-created_at')[:10]
    )
    return render(request, 'accounts/users.html', {
        'users': users,
        'businesses': businesses,
        'payments': payments,
    })
