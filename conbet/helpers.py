# -*- coding: utf-8 -*-
### Aux functions
from conbet.models import Match, Bet, GroupMatch, Round, Group, Qualification, Result, Team
from django.contrib.auth.models import User
from django.conf import settings

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
