import json

from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseServerError
from django.shortcuts import get_list_or_404, get_object_or_404, render_to_response
from django.contrib.auth.models import User

from conbet.models import Match, Bet, GroupMatch, Round

@login_required
def index(request):
    if settings.BETTING:
        return edit_bet(request)
    else:
        return ranking(request)

@login_required
def ranking(request):
    raise Http404

@login_required
def edit_bet(request):
    if request.method == 'POST':
        update_bet(request)
    return show_user_bet(request.user, True) 

@login_required
def bet(request, username):
    user = get_object_or_404(User, username=username)
    return show_user_bet(user, False)

@login_required
def results(request):
    raise Http404

### Aux functions

def show_user_bet(user, editable):
    bets = Bet.objects.filter(owner=user)
    group_matches = GroupMatch.objects.all().order_by('group__name', 'date')
    rounds = Round.objects.all().order_by('stage', 'order')
    return render_to_response('bet.html', {'bets': bets, 'group_matches':
         group_matches, 'round_matches': rounds, 'editable': editable})

def update_bet(request):
    try:
        bet_info = json.loads(request.POST.get('bets'))
        for (match_id, match_info) in bet_info.items():
            match = Match.objects.get(id=match_id)
            bet = Bet.objects.get(owner=request.user, match=match)
            if not bet:
                bet = Bet(owner=request.user, match=match)
            bet.home_goals = match_info['home_goals']
            bet.visitor_goals = match_info['visitor_goals']
            bet.winner = match_info['winner']
            bet.save()        
    except e:
        raise HttpResponseServerError("Something happened %s" % e) 
