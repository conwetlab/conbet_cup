# -*- coding: utf-8 -*-
import json

from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseForbidden, HttpResponseServerError, HttpResponseRedirect
from django.shortcuts import get_list_or_404, get_object_or_404, render_to_response
from django.contrib.auth.models import User
from django.template import RequestContext

from conbet.models import Match, Bet, GroupMatch, Round, Group, Qualification, Result, Team

def index(request):
    if settings.BETTING:
        if request.user.is_authenticated():
            return edit_bet(request)
        else:
            return HttpResponseRedirect("login/?next=/")
    else:
        return ranking(request)

def ranking(request):
    users = []
    position = 0
    last_points = None
    for user in User.objects.all():
        points = total_score(user)
        users.append({
            'points': points,
            'name': user.username,
            'firstname': user.first_name,
            'lastname': user.last_name,
        })
    users = sorted(users, key=lambda x: -x['points'])
    for user in users:
        if user["points"] != last_points:
            last_points = user["points"]
            position += 1
        user["position"] = position
    settings.PRIZES.set_prizes(users)
    
    return render_to_response('ranking.html', { 'users': users },
        context_instance=RequestContext(request))


@login_required
def edit_bet(request):
    if request.method == 'POST':
        update_bet(request)
    return bet(request, request.user.username, editable=True) 


@login_required
def bet(request, username, editable=False):
    user = get_object_or_404(User, username=username)
    if user != request.user and settings.BETTING:
        return HttpResponseForbidden()

    stages = Round.objects.values('stage').distinct().order_by('-stage')
    rounds = []
    for s in stages:
        stage = s['stage']
        rounds.append([
            Round.STAGE_NAMES[stage],
            Round.objects.filter(stage=stage).order_by('order'),
            ])

    bets = []
    for match in Match.objects.all():
        bet, created = Bet.objects.get_or_create(owner=user, match=match)
        bets.append(bet)

    return render_to_response('bet.html', {
        'groups': Group.objects.all().order_by('name'),
        'qualifications': Qualification.objects.all(),
        'teams': Team.objects.all(),
        'bets': bets,
        'rounds': rounds,
        'valid_goals': range(settings.MAX_GOALS+1),
        'editable': editable,
        'points': score_bet(user),
        'total_score': total_score(user),
    }, context_instance=RequestContext(request))


@login_required
def results(request):
    stages = Round.objects.values('stage').distinct().order_by('-stage')
    rounds = []
    for s in stages:
        stage = s['stage']
        rounds.append([
            Round.STAGE_NAMES[stage],
            Round.objects.filter(stage=stage).order_by('order'),
            ])

    return render_to_response('bet.html', {
        'groups': Group.objects.all().order_by('name'),
        'teams': Team.objects.all(),
        'bets': Match.objects.all(),
        'rounds': rounds,
        'editable': False,
    }, context_instance=RequestContext(request))


def rank_group(request, groupname):
    if not request.user.is_authenticated():
        return HttpResponseForbidden()
    group_matches = json.loads(request.POST.get('matches'))

    group = get_object_or_404(Group, name=groupname)
    teams = group.team_set.all()
    results = []
    for match_info in group_matches:
        match = group.groupmatch_set.get(id=match_info["id"])
        results.append(Result(home=match.home, visitor=match.visitor,
            home_goals=match_info['home_goals'], 
            visitor_goals=match_info['visitor_goals'],
            winner=match_info['winner']))

    ranking = settings.RULES.rank_group(teams, results, with_points=True)
    return HttpResponse(json.dumps(map(lambda t: (t[0].code, t[1]), ranking)),
        content_type="text/json")

### Aux functions


def update_bet(request):
    bet_info = json.loads(request.POST.get('bets'))
    for (match_id, match_info) in bet_info.items():
        match = Match.objects.get(id=match_id)
        bet,created = Bet.objects.get_or_create(owner=request.user, match=match)
        bet.home_goals = match_info['home_goals']
        bet.visitor_goals = match_info['visitor_goals']
        if bet.home_goals > bet.visitor_goals:
            bet.winner = 'H'
        elif bet.home_goals < bet.visitor_goals:
            bet.winner = 'V'
        else:
            try:
                group_match = GroupMatch.objects.get(id=match.id)
                bet.winner = 'T'
            except GroupMatch.DoesNotExist: 
                bet.winner = match_info['winner']
        bet.save()

    cache_bet_teams(request.user)

def cache_bet_teams(user):
    # group classification
    for group in Group.objects.all():

        group_bets = []
        for match in GroupMatch.objects.filter(group=group):
            bet = get_object_or_404(Bet, match=match, owner=user)
            bet.home = match.home 
            bet.visitor = match.visitor
            bet.save()
            group_bets.append(bet)

        ranking = settings.RULES.rank_group(
            group.team_set.all(),
            group_bets
        )
        
        for q in Qualification.objects.filter(group=group):
            bet = user.bet_set.get(match=q.qualify_for)
            team = ranking[q.position-1]
            if team:
                #print(u'%s qualifies for %s (%s)' % (
                #    team, q.qualify_for, q.side,
                #))

                if q.side == 'H':
                    bet.home = team
                else:
                    bet.visitor = team
                bet.save()

    # round classification
    for q in Qualification.objects.filter(group=None).order_by('id'):
        team = Bet.objects.get(owner=user, 
                               match=q.round).get_position(q.position)
        bet = Bet.objects.get(owner=user, match=q.qualify_for)
        if team:
            #print("%d-th %s (%s) qualifies for %s (%s)" % (
            #    q.position, q.round, team, q.qualify_for, q.side,
            #))
            if q.side == 'H':
                bet.home = team
            else:
                bet.visitor = team
            bet.save()


def group_list(list):
    """Group a tuple list by the first element into a dict."""
    result = {}
    for element in list:
        key = element[0]
        if key in result:
            result[key].append(element[1:])
        else:
            result[key] = [element[1:]]
    return result


def score_bet(user):
    sr = settings.SCORE_RULES
    match_points = []
    group_points = []
    for group in Group.objects.all():
        played_matches = group.groupmatch_set.filter(winner__isnull=False)
        for groupmatch in played_matches:
            try:
                bet = Bet.objects.get(owner=user, match=groupmatch)
                match_points += map(lambda x: (groupmatch.id, x[0], x[1]),
                    sr.score_group_match(bet, groupmatch))
            except Bet.DoesNotExist:
                pass # partial bet

        if len(group.groupmatch_set.filter(winner__isnull=True)) == 0:
            bet_matches = []
            for match in GroupMatch.objects.filter(group=group):
                try:
                    bet = Bet.objects.get(match=match,owner=user)
                    bet_matches.append(bet)
                except Bet.DoesNotExist, e:
                    pass # partial bet

            guessed_ranking = settings.RULES.rank_group(
                group.team_set.all(),
                bet_matches,
            )
            ranking = settings.RULES.rank_group(
                group.team_set.all(),
                group.groupmatch_set.all(),
            )
            group_points += map(lambda x: (group.name, x[0], x[1]),
                sr.score_group_classification(guessed_ranking, ranking))

    for round in Round.objects.filter(winner__isnull=False):
        try:
            bet = Bet.objects.get(owner=user, match=round)
            match_points += map(lambda x: (round.id, x[0], x[1]),
                                sr.score_round(bet, round))
        except Bet.DoesNotExist:
            pass # partial bet
    
    # The final
    try:
        final = Round.objects.get(stage=1,order=1)
        bet = Bet.objects.get(owner=user, match=final)
        match_points += map(lambda x: ('winner', x[0], x[1]),
                            sr.score_cup_winner(bet, final))
    except Bet.DoesNotExist, Round.DoesNotExist:
        pass

    return { 'match_points': group_list(match_points),
             'group_points': group_list(group_points), }


def total_score(user):
    bet = score_bet(user)
    total_score = 0
    for scores in bet['match_points'].values() + bet['group_points'].values():
        for score in scores:
            total_score += score[0]
    return total_score
