---
layout: page
title: Presentations & Talks
subtitle: Sharing knowledge on data, cloud, and engineering
---

Below are presentations and talks I have given or am scheduled to give.

<div class="presentations-list">
{% assign sorted_presentations = site.presentations | sort: 'sort_date' | reverse %}
{% for presentation in sorted_presentations %}
  <div class="presentation-item">
    <h3><a href="{{ presentation.session_url | default: presentation.event_url }}" target="_blank" rel="noopener noreferrer">{{ presentation.title }}</a></h3>
    <p>
      <strong>Event:</strong> <a href="{{ presentation.event_url }}" target="_blank" rel="noopener noreferrer">{{ presentation.event }}</a> <br>
      <strong>Location:</strong> {{ presentation.location }} | 
      <strong>Date(s):</strong> {{ presentation.dates }} | 
      <strong>Status:</strong> {{ presentation.status }}
    </p>
    {% if presentation.speakers %}
      <p><strong>Speakers:</strong> {{ presentation.speakers | join: ", " }}</p>
    {% endif %}
    <p>{{ presentation.description | markdownify }}</p>
    {% if presentation.technologies %}
      <p><em>Technologies: {{ presentation.technologies }}</em></p>
    {% endif %}
    <!-- Add links to slides/video when available -->
    <!-- 
    <p>
      {% if presentation.slides_url %}<a href="{{ presentation.slides_url }}">[Slides]</a> {% endif %}
      {% if presentation.video_url %}<a href="{{ presentation.video_url }}">[Video]</a>{% endif %}
    </p>
    -->
    <hr style="margin-top: 2em; margin-bottom: 2em;">
  </div>
{% endfor %}
</div>

<!-- Basic styling suggestion (similar to projects) -->
<!--
<style>
.presentations-list .presentation-item {
  margin-bottom: 2.5em;
}
.presentations-list h3 {
  margin-bottom: 0.25em;
}
.presentations-list h3 a {
  color: inherit;
}
.presentations-list p {
  margin-top: 0.5em;
  margin-bottom: 0.5em;
}
</style>
--> 