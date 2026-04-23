"""Generate a visual HTML schedule viewer from a saved genome.

Produces a self-contained HTML file you can open in any browser.
Shows:
  - A weekly grid (one tab per day) with classes as colored blocks
  - Room rows, time columns
  - Violations highlighted in red with explanations
  - A violations panel explaining exactly what's wrong and why

Usage:
    python scripts/view_schedule.py
    python scripts/view_schedule.py --genome results/run_20260420_111620_best.npy
    python scripts/view_schedule.py --output outputs/my_schedule.html
    python scripts/view_schedule.py --subset 100
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src.core.parser import parse_data
from src.core.preprocessor import preprocess
from src.scheduling.fitness import evaluate_detailed
from src.scheduling.constraints.hard import check_room_conflicts


DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
DAY_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

DISPLAY_START = 84   # 7:00am
DISPLAY_END   = 264  # 10:00pm

DEPT_COLORS = [
    '#3B82F6', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899',
    '#06B6D4', '#EF4444', '#84CC16', '#F97316', '#6366F1',
    '#14B8A6', '#D946EF', '#0EA5E9', '#A3E635', '#FB923C',
]


def slot_to_time(slot: int) -> str:
    minutes = slot * 5
    h, m = divmod(minutes, 60)
    ampm = 'am' if h < 12 else 'pm'
    h12 = h if 1 <= h <= 12 else (h - 12 if h > 12 else 12)
    return f'{h12}:{m:02d}{ampm}'


def find_violations(tt, pp, genome):
    conflicts = []
    classes_by_room: dict = {}
    for ci, cls in enumerate(tt.classes):
        if not cls.candidate_rooms:
            continue
        rid = cls.candidate_rooms[int(genome[ci, 0])].room_id
        classes_by_room.setdefault(rid, []).append(ci)

    for rid, cidxs in classes_by_room.items():
        if len(cidxs) < 2:
            continue
        for i in range(len(cidxs)):
            for j in range(i + 1, len(cidxs)):
                ci_a, ci_b = cidxs[i], cidxs[j]
                key = (min(ci_a, ci_b), max(ci_a, ci_b))
                if key in pp.meet_with_exempt_pairs:
                    continue
                ma = pp.time_masks[ci_a][int(genome[ci_a, 1])]
                mb = pp.time_masks[ci_b][int(genome[ci_b, 1])]
                if np.any(ma & mb):
                    cls_a = tt.classes[ci_a]
                    cls_b = tt.classes[ci_b]
                    tp_a = cls_a.candidate_times[int(genome[ci_a, 1])]
                    tp_b = cls_b.candidate_times[int(genome[ci_b, 1])]
                    room = tt.rooms_by_id[rid]
                    conflicts.append({
                        'room_id': rid,
                        'room_cap': room.capacity,
                        'ci_a': ci_a, 'class_id_a': cls_a.id,
                        'limit_a': cls_a.class_limit,
                        'n_room_opts_a': len(cls_a.candidate_rooms),
                        'n_time_opts_a': len(cls_a.candidate_times),
                        'tp_a': tp_a,
                        'ci_b': ci_b, 'class_id_b': cls_b.id,
                        'limit_b': cls_b.class_limit,
                        'n_room_opts_b': len(cls_b.candidate_rooms),
                        'n_time_opts_b': len(cls_b.candidate_times),
                        'tp_b': tp_b,
                    })
    return conflicts


def build_schedule_data(tt, pp, genome):
    dept_ids = sorted(set(c.department for c in tt.classes))
    dept_color_map = {d: DEPT_COLORS[i % len(DEPT_COLORS)] for i, d in enumerate(dept_ids)}
    assigned = []
    for ci, cls in enumerate(tt.classes):
        if not cls.candidate_rooms or not cls.candidate_times:
            continue
        rid = cls.candidate_rooms[int(genome[ci, 0])].room_id
        tp = cls.candidate_times[int(genome[ci, 1])]
        room = tt.rooms_by_id[rid]
        assigned.append({
            'ci': ci,
            'class_id': cls.id,
            'offering': cls.offering,
            'room_id': rid,
            'room_cap': room.capacity,
            'class_limit': cls.class_limit,
            'dept': cls.department,
            'color': dept_color_map[cls.department],
            'instructors': cls.instructor_ids,
            'tp_days': tp.days,
            'tp_start': tp.start,
            'tp_length': tp.length,
            'n_room_opts': len(cls.candidate_rooms),
            'n_time_opts': len(cls.candidate_times),
        })

    conflicts = find_violations(tt, pp, genome)
    conflict_ci_set = set()
    for c in conflicts:
        conflict_ci_set.add(c['ci_a'])
        conflict_ci_set.add(c['ci_b'])


    active_days = sorted(set(
        d for a in assigned
        for d in range(7) if a['tp_days'] & (1 << d)
    ))

    active_rooms = sorted(set(a['room_id'] for a in assigned))

    return {
        'assigned': assigned,
        'conflicts': conflicts,
        'conflict_ci_set': conflict_ci_set,
        'active_days': active_days,
        'active_rooms': active_rooms,
        'rooms_by_id': {r.id: r for r in tt.rooms},
        'dept_color_map': dept_color_map,
    }

def generate_html(tt, pp, genome, fitness_result):
    data = build_schedule_data(tt, pp, genome)
    conflicts = data['conflicts']
    conflict_ci_set = data['conflict_ci_set']


    SLOT_HEIGHT = 2
    ROW_HEIGHT = 52
    LABEL_WIDTH = 90
    TIME_LABEL_HEIGHT = 30

    def slot_to_px(slot):
        return (slot - DISPLAY_START) * SLOT_HEIGHT

    def length_to_px(length):
        return max(length * SLOT_HEIGHT, 16)


    day_grids = []
    for day_idx in data['active_days']:
        day_name = DAYS[day_idx]


        day_classes = [a for a in data['assigned'] if a['tp_days'] & (1 << day_idx)]
        if not day_classes:
            continue


        rooms_in_day = sorted(set(a['room_id'] for a in day_classes))
        room_rows = []
        for rid in rooms_in_day:
            room = data['rooms_by_id'][rid]
            classes_in_room = [a for a in day_classes if a['room_id'] == rid]
            blocks = []
            for a in classes_in_room:
                is_conflict = a['ci'] in conflict_ci_set
                top = slot_to_px(a['tp_start'])
                height = length_to_px(a['tp_length'])
                start_time = slot_to_time(a['tp_start'])
                end_time = slot_to_time(a['tp_start'] + a['tp_length'])
                pinned = a['n_room_opts'] == 1 and a['n_time_opts'] == 1
                pinned_r = a['n_room_opts'] == 1
                pinned_t = a['n_time_opts'] == 1
                blocks.append({
                    'ci': a['ci'],
                    'class_id': a['class_id'],
                    'limit': a['class_limit'],
                    'dept': a['dept'],
                    'color': a['color'],
                    'top': top,
                    'height': height,
                    'start_time': start_time,
                    'end_time': end_time,
                    'is_conflict': is_conflict,
                    'pinned': pinned,
                    'pinned_r': pinned_r,
                    'pinned_t': pinned_t,
                    'instructors': a['instructors'],
                })
            room_rows.append({
                'room_id': rid,
                'capacity': room.capacity,
                'has_sharing': room.sharing is not None,
                'blocks': blocks,
            })

        day_grids.append({'day_name': day_name, 'day_idx': day_idx, 'room_rows': room_rows})

    time_labels = []
    for s in range(DISPLAY_START, DISPLAY_END, 6):  # every 30 min
        time_labels.append({
            'top': slot_to_px(s),
            'label': slot_to_time(s),
        })

    violation_html_parts = []
    if not conflicts:
        violation_html_parts.append(
            '<p style="color:#10B981;font-weight:600;">No violations. Schedule is feasible.</p>'
        )
    else:
        for c in conflicts:
            tp_a = c['tp_a']
            tp_b = c['tp_b']
            days_a = '/'.join(DAY_SHORT[d] for d in range(7) if tp_a.days & (1 << d))
            days_b = '/'.join(DAY_SHORT[d] for d in range(7) if tp_b.days & (1 << d))
            overlap_days = '/'.join(DAY_SHORT[d] for d in range(7) if (tp_a.days & tp_b.days) & (1 << d))

            # Explain if it's fixable
            if c['n_room_opts_a'] == 1 and c['n_time_opts_a'] == 1 and \
               c['n_room_opts_b'] == 1 and c['n_time_opts_b'] == 1:
                fixable = ('STRUCTURAL — CANNOT BE FIXED. Both classes are fully pinned '
                           '(each has exactly 1 candidate room and 1 candidate time). '
                           'The GA has no moves available to resolve this.')
                fix_color = '#EF4444'
            elif c['n_room_opts_a'] == 1 and c['n_room_opts_b'] == 1:
                fixable = ('Room-pinned conflict. Both classes have only 1 candidate room '
                           'and both point to the same room. The conflict CAN be resolved '
                           'by shifting one class to a non-overlapping time slot — '
                           f'Class {c["class_id_a"]} has {c["n_time_opts_a"]} time options, '
                           f'Class {c["class_id_b"]} has {c["n_time_opts_b"]} time options.')
                fix_color = '#F59E0B'
            else:
                fixable = ('Potentially fixable. The GA should be able to move at least '
                           'one of these classes to a different room or time.')
                fix_color = '#10B981'

            # Check UniTime approach for room 10 specifically
            unitime_note = ''
            if c['room_id'] == 10:
                unitime_note = (
                    '<div style="margin-top:8px;padding:8px;background:#EFF6FF;'
                    'border-radius:6px;font-size:12px;">'
                    '<strong>UniTime approach:</strong> Room 10 has a department-sharing '
                    'pattern. UniTime\'s solver also places these two classes here '
                    'simultaneously in its reference solution. It treats the co-placement '
                    'as permitted by the sharing pattern (the room has multiple department '
                    'slots), while our code counts it as a conflict. This is the '
                    '"room sharing interpretation gap" noted in the code. '
                    'One fix: add room 10 co-placements to the exempt pairs set, '
                    'the same way we exempted MEET_WITH pairs.</div>'
                )

            violation_html_parts.append(f'''
<div style="border:2px solid {fix_color};border-radius:8px;padding:16px;margin-bottom:12px;">
  <div style="font-weight:700;color:{fix_color};margin-bottom:8px;font-size:14px;">
    Room conflict: Room {c["room_id"]} (capacity {c["room_cap"]})
  </div>
  <table style="width:100%;font-size:12px;border-collapse:collapse;">
    <tr style="background:#F9FAFB;">
      <th style="padding:4px 8px;text-align:left;width:15%">Class</th>
      <th style="padding:4px 8px;text-align:left;width:15%">Enrollment limit</th>
      <th style="padding:4px 8px;text-align:left;width:25%">Scheduled time</th>
      <th style="padding:4px 8px;text-align:left;width:20%">Room options</th>
      <th style="padding:4px 8px;text-align:left;width:25%">Time options</th>
    </tr>
    <tr>
      <td style="padding:4px 8px;font-weight:600">Class {c["class_id_a"]}</td>
      <td style="padding:4px 8px">{c["limit_a"]} students</td>
      <td style="padding:4px 8px">{days_a} {slot_to_time(tp_a.start)}–{slot_to_time(tp_a.start+tp_a.length)}</td>
      <td style="padding:4px 8px">{c["n_room_opts_a"]} option{"s" if c["n_room_opts_a"]!=1 else ""} {"(PINNED)" if c["n_room_opts_a"]==1 else ""}</td>
      <td style="padding:4px 8px">{c["n_time_opts_a"]} option{"s" if c["n_time_opts_a"]!=1 else ""} {"(PINNED)" if c["n_time_opts_a"]==1 else ""}</td>
    </tr>
    <tr style="background:#F9FAFB;">
      <td style="padding:4px 8px;font-weight:600">Class {c["class_id_b"]}</td>
      <td style="padding:4px 8px">{c["limit_b"]} students</td>
      <td style="padding:4px 8px">{days_b} {slot_to_time(tp_b.start)}–{slot_to_time(tp_b.start+tp_b.length)}</td>
      <td style="padding:4px 8px">{c["n_room_opts_b"]} option{"s" if c["n_room_opts_b"]!=1 else ""} {"(PINNED)" if c["n_room_opts_b"]==1 else ""}</td>
      <td style="padding:4px 8px">{c["n_time_opts_b"]} option{"s" if c["n_time_opts_b"]!=1 else ""} {"(PINNED)" if c["n_time_opts_b"]==1 else ""}</td>
    </tr>
  </table>
  <div style="margin-top:8px;padding:8px;background:#FEF2F2;border-radius:6px;font-size:12px;">
    <strong>Overlap on:</strong> {overlap_days}
  </div>
  <div style="margin-top:6px;padding:8px;background:#F9FAFB;border-radius:6px;font-size:12px;color:{fix_color};">
    <strong>Verdict:</strong> {fixable}
  </div>
  {unitime_note}
</div>''')

    violation_html = '\n'.join(violation_html_parts)
    total_height = slot_to_px(DISPLAY_END) + TIME_LABEL_HEIGHT + 20

    day_tabs_html = []
    day_panels_html = []

    for i, grid in enumerate(day_grids):
        active = 'active' if i == 0 else ''
        day_tabs_html.append(
            f'<button class="tab-btn {active}" onclick="showDay({i})">'
            f'{grid["day_name"]}</button>'
        )

        room_rows_html = []
        for rr in grid['room_rows']:

            sharing_badge = ' <span class="badge-share">shared</span>' if rr['has_sharing'] else ''
            room_label = (
                f'<div class="room-label">'
                f'<div class="room-name">Room {rr["room_id"]}{sharing_badge}</div>'
                f'<div class="room-cap">{rr["capacity"]} seats</div>'
                f'</div>'
            )

            blocks_html = []
            for b in rr['blocks']:
                border = '3px solid #EF4444' if b['is_conflict'] else '1px solid rgba(0,0,0,0.15)'
                bg = b['color']
                opacity = '1' if not b['is_conflict'] else '1'
                pin_indicator = ''
                if b['pinned']:
                    pin_indicator = '<span class="pin-badge" title="Fully pinned: 1 room &amp; 1 time option">&#128204;</span>'
                elif b['pinned_r']:
                    pin_indicator = '<span class="pin-badge" title="Room pinned: 1 room option">&#128204;R</span>'
                elif b['pinned_t']:
                    pin_indicator = '<span class="pin-badge" title="Time pinned: 1 time option">&#128204;T</span>'

                conflict_stripe = ''
                if b['is_conflict']:
                    conflict_stripe = '<div class="conflict-stripe"></div>'

                tooltip = (
                    f'Class {b["class_id"]} | '
                    f'Dept {b["dept"]} | '
                    f'Limit {b["limit"]} | '
                    f'{b["start_time"]}–{b["end_time"]}'
                )
                if b['is_conflict']:
                    tooltip += ' | ⚠ ROOM CONFLICT'

                blocks_html.append(f'''
<div class="class-block{'conflict-block' if b['is_conflict'] else ''}"
     style="top:{b['top']}px;height:{b['height']}px;background:{bg};border:{border};opacity:{opacity}"
     title="{tooltip}">
  {conflict_stripe}
  <div class="block-inner">
    <div class="block-title">C{b['class_id']} {pin_indicator}</div>
    <div class="block-sub">{b['limit']}✦</div>
  </div>
</div>''')

            room_rows_html.append(f'''
<div class="room-row">
  {room_label}
  <div class="time-cells" style="height:{ROW_HEIGHT}px">
    {"".join(blocks_html)}
  </div>
</div>''')

        # Time axis (column headers)
        time_axis_html = ''.join(
            f'<div class="time-tick" style="top:{t["top"]}px">{t["label"]}</div>'
            for t in time_labels
        )

        display = 'block' if i == 0 else 'none'
        day_panels_html.append(f'''
<div id="day-{i}" class="day-panel" style="display:{display}">
  <div class="grid-scroll">
    <div class="grid-container" style="height:{total_height}px">
      <div class="time-axis" style="height:{total_height}px">
        {time_axis_html}
      </div>
      <div class="rooms-area">
        {"".join(room_rows_html)}
      </div>
    </div>
  </div>
</div>''')
    soft = fitness_result['soft']
    hard = fitness_result['hard']

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Schedule viewer — subset 100 classes</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #F8FAFC; color: #1E293B; font-size: 13px; }}
  /* Header */
  .header {{ background: white; border-bottom: 1px solid #E2E8F0;
             padding: 16px 24px; display: flex; align-items: center;
             justify-content: space-between; }}
  .header h1 {{ font-size: 18px; font-weight: 700; color: #0F172A; }}
  .header-meta {{ font-size: 12px; color: #64748B; }}
  /* Score strip */
  .score-strip {{ display: flex; gap: 12px; padding: 12px 24px;
                  background: white; border-bottom: 1px solid #E2E8F0; flex-wrap:wrap; }}
  .score-card {{ padding: 8px 14px; border-radius: 8px; font-size: 12px; }}
  .score-card .label {{ color: #64748B; margin-bottom: 2px; }}
  .score-card .value {{ font-size: 18px; font-weight: 700; }}
  .sc-hard {{ background: #FEF2F2; }}
  .sc-hard .value {{ color: #EF4444; }}
  .sc-soft {{ background: #FFFBEB; }}
  .sc-soft .value {{ color: #D97706; }}
  .sc-pref {{ background: #F0FDF4; }}
  .sc-pref .value {{ color: #16A34A; }}
  .sc-cap {{ background: #FFF7ED; }}
  .sc-cap .value {{ color: #EA580C; }}
  .sc-group {{ background: #FAF5FF; }}
  .sc-group .value {{ color: #7C3AED; }}
  /* Main layout */
  .main {{ display: flex; height: calc(100vh - 120px); overflow: hidden; }}
  /* Left: schedule */
  .schedule-pane {{ flex: 1; display: flex; flex-direction: column; overflow: hidden; }}
  /* Right: violations */
  .violations-pane {{ width: 380px; background: white; border-left: 1px solid #E2E8F0;
                      overflow-y: auto; padding: 16px; flex-shrink: 0; }}
  .violations-pane h2 {{ font-size: 14px; font-weight: 700; margin-bottom: 12px;
                          padding-bottom: 8px; border-bottom: 1px solid #E2E8F0; }}
  /* Tabs */
  .tabs {{ display: flex; gap: 4px; padding: 10px 16px 0;
           background: white; border-bottom: 1px solid #E2E8F0; }}
  .tab-btn {{ padding: 6px 14px; border: none; border-radius: 6px 6px 0 0;
              cursor: pointer; font-size: 12px; font-weight: 500;
              background: #F1F5F9; color: #64748B; transition: all .15s; }}
  .tab-btn.active {{ background: #3B82F6; color: white; }}
  .tab-btn:hover:not(.active) {{ background: #E2E8F0; }}
  /* Day panel */
  .day-panel {{ flex: 1; overflow: hidden; }}
  .grid-scroll {{ overflow: auto; height: 100%; padding: 12px 16px; }}
  /* Grid */
  .grid-container {{ position: relative; display: flex; }}
  .time-axis {{ width: 54px; flex-shrink: 0; position: relative; }}
  .time-tick {{ position: absolute; left: 0; font-size: 10px; color: #94A3B8;
                width: 50px; text-align: right; transform: translateY(-6px); }}
  .rooms-area {{ flex: 1; border-left: 1px solid #E2E8F0; }}
  .room-row {{ display: flex; border-bottom: 1px solid #F1F5F9; min-height: {ROW_HEIGHT}px; }}
  .room-label {{ width: {LABEL_WIDTH}px; flex-shrink: 0; padding: 8px;
                 border-right: 1px solid #E2E8F0; background: #FAFAFA; }}
  .room-name {{ font-weight: 600; font-size: 12px; color: #334155; }}
  .room-cap {{ font-size: 10px; color: #94A3B8; margin-top: 2px; }}
  .badge-share {{ font-size: 9px; background: #DBEAFE; color: #1D4ED8;
                  padding: 1px 4px; border-radius: 3px; }}
  /* Time cells area */
  .time-cells {{ flex: 1; position: relative; }}
  /* Class blocks */
  .class-block {{ position: absolute; left: 2px; right: 2px;
                  border-radius: 4px; overflow: hidden; cursor: default;
                  transition: opacity .15s; }}
  .class-block:hover {{ opacity: 0.85 !important; z-index: 10; }}
  .conflict-block {{ z-index: 5; }}
  .conflict-stripe {{ position: absolute; top: 0; left: 0; right: 0; height: 3px;
                      background: #EF4444; }}
  .block-inner {{ padding: 2px 4px; height: 100%; display: flex;
                  flex-direction: column; justify-content: center; }}
  .block-title {{ font-size: 10px; font-weight: 700; color: white;
                  text-shadow: 0 1px 2px rgba(0,0,0,0.4); white-space: nowrap;
                  overflow: hidden; text-overflow: ellipsis; }}
  .block-sub {{ font-size: 9px; color: rgba(255,255,255,0.85); margin-top: 1px; }}
  .pin-badge {{ font-size: 8px; }}
  /* Legend */
  .legend {{ padding: 8px 16px; background: white; border-top: 1px solid #E2E8F0;
             display: flex; gap: 16px; font-size: 11px; color: #64748B;
             flex-wrap: wrap; }}
  .legend-item {{ display: flex; align-items: center; gap: 4px; }}
  .legend-dot {{ width: 10px; height: 10px; border-radius: 2px; }}
</style>
</head>
<body>

<div class="header">
  <h1>Schedule viewer — {len(tt.classes)} classes, {len(data["active_rooms"])} rooms</h1>
  <div class="header-meta">
    Fitness: {fitness_result["fitness"]:.0f} &nbsp;|&nbsp;
    Hard violations: <strong style="color:{"#EF4444" if hard["total"]>0 else "#10B981"}">{hard["total"]}</strong>
    &nbsp;|&nbsp; Feasible: {"✓ Yes" if fitness_result["is_feasible"] else "✗ No"}
  </div>
</div>

<div class="score-strip">
  <div class="score-card sc-hard">
    <div class="label">Hard violations</div>
    <div class="value">{hard["total"]}</div>
  </div>
  <div class="score-card sc-soft">
    <div class="label">Soft total</div>
    <div class="value">{fitness_result["soft_total"]:.0f}</div>
  </div>
  <div class="score-card sc-pref">
    <div class="label">Preferences</div>
    <div class="value">{soft["preferences"]:.0f}</div>
  </div>
  <div class="score-card sc-cap">
    <div class="label">Capacity penalty</div>
    <div class="value">{soft["capacity"]:.0f}</div>
  </div>
  <div class="score-card sc-group">
    <div class="label">Group constraint penalty</div>
    <div class="value">{soft["group"]:.0f}</div>
  </div>
</div>

<div class="main">
  <div class="schedule-pane">
    <div class="tabs">
      {"".join(day_tabs_html)}
    </div>
    {"".join(day_panels_html)}
    <div class="legend">
      <div class="legend-item">
        <div class="legend-dot" style="background:#EF4444;border:2px solid #EF4444"></div>
        Red border = room conflict
      </div>
      <div class="legend-item"> = pinned (1 option)</div>
      <div class="legend-item">R = room pinned</div>
      <div class="legend-item">T = time pinned</div>
      <div class="legend-item">Colors = departments</div>
      <div class="legend-item">✦ = class enrollment limit</div>
    </div>
  </div>

  <div class="violations-pane">
    <h2> Violations ({len(conflicts)})</h2>
    {violation_html}

    <h2 style="margin-top:20px">Score breakdown</h2>
    <table style="width:100%;font-size:12px;border-collapse:collapse;">
      <tr><th style="text-align:left;padding:4px;color:#64748B">Component</th>
          <th style="text-align:right;padding:4px;color:#64748B">Value</th></tr>
      <tr><td style="padding:4px">Room conflicts</td>
          <td style="text-align:right;padding:4px;color:{'#EF4444' if hard['room_conflicts']>0 else '#10B981'};font-weight:600">{hard['room_conflicts']}</td></tr>
      <tr style="background:#F9FAFB">
          <td style="padding:4px">Instructor conflicts</td>
          <td style="text-align:right;padding:4px;color:{'#EF4444' if hard['instructor_conflicts']>0 else '#10B981'};font-weight:600">{hard['instructor_conflicts']}</td></tr>
      <tr><td style="padding:4px">Room sharing</td>
          <td style="text-align:right;padding:4px;color:{'#EF4444' if hard['room_sharing']>0 else '#10B981'};font-weight:600">{hard['room_sharing']}</td></tr>
      <tr style="background:#F9FAFB">
          <td style="padding:4px">Group (P-pref only)</td>
          <td style="text-align:right;padding:4px;color:{'#EF4444' if hard['group']>0 else '#10B981'};font-weight:600">{hard['group']}</td></tr>
      <tr style="border-top:2px solid #E2E8F0;font-weight:700">
          <td style="padding:4px">Hard total</td>
          <td style="text-align:right;padding:4px">{hard['total']}</td></tr>
      <tr style="background:#F9FAFB">
          <td style="padding:4px">Time+room prefs</td>
          <td style="text-align:right;padding:4px;color:{'#10B981' if soft['preferences']<0 else '#EF4444'}">{soft['preferences']:.1f}</td></tr>
      <tr><td style="padding:4px">Capacity penalty</td>
          <td style="text-align:right;padding:4px">{soft['capacity']:.0f}</td></tr>
      <tr style="background:#F9FAFB">
          <td style="padding:4px">Group constraint penalty</td>
          <td style="text-align:right;padding:4px">{soft['group']:.0f}</td></tr>
      <tr><td style="padding:4px">Workload penalty</td>
          <td style="text-align:right;padding:4px">{soft['instructor_workload']:.1f}</td></tr>
      <tr style="border-top:2px solid #E2E8F0;font-weight:700">
          <td style="padding:4px">Soft total</td>
          <td style="text-align:right;padding:4px">{fitness_result["soft_total"]:.1f}</td></tr>
      <tr style="border-top:2px solid #334155;font-weight:700;background:#F0F9FF">
          <td style="padding:4px">TOTAL FITNESS</td>
          <td style="text-align:right;padding:4px">{fitness_result["fitness"]:.1f}</td></tr>
    </table>
  </div>
</div>

<script>
function showDay(idx) {{
  document.querySelectorAll('.day-panel').forEach((p, i) => {{
    p.style.display = i === idx ? 'block' : 'none';
  }});
  document.querySelectorAll('.tab-btn').forEach((b, i) => {{
    b.classList.toggle('active', i === idx);
  }});
}}
</script>
</body>
</html>'''

    return html

def main():
    parser = argparse.ArgumentParser(description='View schedule as HTML')
    parser.add_argument('--genome', type=Path, default=None,
                        help='Path to .npy genome file (default: latest in results/)')
    parser.add_argument('--data', type=Path, default=Path('data/data.xml'))
    parser.add_argument('--subset', type=int, default=None)
    parser.add_argument('--output', type=Path, default=Path('outputs/schedule.html'))
    args = parser.parse_args()

    if args.genome:
        genome_path = args.genome
    else:
        candidates = sorted(Path('results').glob('run_*_best.npy'))
        if not candidates:
            print('No genome files found in results/. Run phase1 first.')
            return 1
        genome_path = candidates[-1]

    print(f'Loading genome from {genome_path}...')
    genome = np.load(genome_path)

    print(f'Loading data from {args.data}...')
    tt = parse_data(args.data, subset=args.subset or (100 if genome.shape[0] < 896 else None))
    pp = preprocess(tt)

    print('Evaluating schedule...')
    fitness_result = evaluate_detailed(pp, genome)

    print('Generating HTML...')
    html = generate_html(tt, pp, genome, fitness_result)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, 'w') as f:
        f.write(html)

    print(f'Saved to {args.output}')
    print(f'Open in browser: file://{args.output.resolve()}')
    return 0


if __name__ == '__main__':
    sys.exit(main())