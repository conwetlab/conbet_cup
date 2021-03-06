from django.contrib import admin

from models import Team, Group, GroupMatch, Round, Qualification, Bet
from conbet import signals


class GroupMatchesInline(admin.TabularInline):
    model = GroupMatch
    extra = 0
    fieldsets = (
        ('Match', {
            'fields': ('date', 'location'),
        }),
        ('Results', {
            'fields': ('home_goals', 'visitor_goals'),
        }),
    )
    ordering = ('date', 'id')

class GroupAdmin(admin.ModelAdmin):
    inlines = [
        GroupMatchesInline,
    ]
    ordering = ('name',)

admin.site.register(Group, GroupAdmin)

class RoundAdmin(admin.ModelAdmin):
    ordering = ('-stage', 'order')
    fieldsets = (
        (None, {
            'fields': ('stage', 'order'),
        }),
        ('Match', {
            'fields': ('home', 'visitor', 'date', 'location'),
        }),
        ('Results', {
            'fields': ('home_goals', 'visitor_goals', 'winner'),
        }),
    )
        
admin.site.register(Round, RoundAdmin)

class TeamAdmin(admin.ModelAdmin):
    ordering = ('name',)

admin.site.register(Team, TeamAdmin)
admin.site.register(Bet)
signals.connect()
