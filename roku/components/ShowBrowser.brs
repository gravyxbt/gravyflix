sub init()
    m.seasons = m.top.FindNode("seasons")
    m.episodes = m.top.FindNode("episodes")
    m.seasonIndex = -1
    m.positions = {}
    m.seasons.ObserveField("itemFocused", "onSeason")
    m.seasons.ObserveField("itemSelected", "focusEpisodes")
    m.episodes.ObserveField("itemFocused", "onEpisodeFocus")
    m.episodes.ObserveField("itemSelected", "onEpisode")
end sub

sub onShow()
    show = m.top.showData
    if show = invalid then return
    m.seasonIndex = -1
    m.positions = {}
    m.top.FindNode("showArt").uri = "pkg:/images/hero-fallback.png"
    if show.backdrop_url <> invalid then m.top.FindNode("showArt").uri = show.backdrop_url
    m.top.FindNode("showTitle").text = show.title
    m.top.FindNode("summary").text = MoviePresentation(show).metadataLine + "  ·  " + SubtitleIndicatorLabel(show.subtitle_summary, true)
    m.top.FindNode("showDescription").text = TitleSummary(show, 260)
    m.top.FindNode("showCast").text = TitleCast(show)
    root = CreateObject("roSGNode", "ContentNode")
    for each season in show.seasons
        root.CreateChild("ContentNode").title = season.title
    end for
    m.seasons.content = root
    if root.GetChildCount() > 0
        m.seasons.jumpToItem = 0
        loadSeason(0)
    end if
end sub

sub onSeason()
    loadSeason(m.seasons.itemFocused)
end sub

sub loadSeason(index as integer)
    if index = m.seasonIndex or index < 0 then return
    if index >= m.top.showData.seasons.Count() then return
    m.seasonIndex = index
    season = m.top.showData.seasons[index]
    m.top.FindNode("episodeHeading").text = UCase(season.title) + "  ·  " + season.episodes.Count().ToStr() + " EPISODES"
    root = CreateObject("roSGNode", "ContentNode")
    for each episode in season.episodes
        item = root.CreateChild("ContentNode")
        item.title = episode.episode_title
    end for
    m.episodes.content = root
    position = m.positions[index.ToStr()]
    if position = invalid then position = 0
    m.episodes.jumpToItem = position
    showPreview(position)
end sub

sub onEpisodeFocus()
    if m.seasonIndex < 0 then return
    m.positions[m.seasonIndex.ToStr()] = m.episodes.itemFocused
    showPreview(m.episodes.itemFocused)
end sub

sub showPreview(index as integer)
    if m.seasonIndex < 0 then return
    season = m.top.showData.seasons[m.seasonIndex]
    if index < 0 or index >= season.episodes.Count() then return
    episode = season.episodes[index]
    text = episode.episode_title
    runtime = RuntimeLabel(MediaNumber(episode.duration))
    if runtime <> "" then text += "  ·  " + runtime
    m.top.FindNode("preview").text = text
    m.top.FindNode("episodeSubtitles").text = SubtitleIndicatorLabel(episode.subtitle_summary)
end sub

sub onEpisode()
    if m.seasonIndex < 0 then return
    season = m.top.showData.seasons[m.seasonIndex]
    index = m.episodes.itemSelected
    if index >= 0 and index < season.episodes.Count()
        m.top.selectedEpisode = season.episodes[index]
        m.top.episodeRequested++
    end if
end sub

sub focusBrowser()
    m.seasons.SetFocus(true)
end sub

sub focusEpisodes()
    if m.seasonIndex >= 0 then m.episodes.SetFocus(true)
end sub

function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    if key = "right" and m.seasons.HasFocus()
        focusEpisodes()
        return true
    end if
    if (key = "left" or key = "back") and m.episodes.HasFocus()
        focusBrowser()
        return true
    end if
    return false
end function

' Keep Back navigation aligned with the episode most recently started by autoplay.
sub selectEpisodeId(id as dynamic)
    show = m.top.showData
    if show = invalid then return
    for seasonIndex = 0 to show.seasons.Count() - 1
        season = show.seasons[seasonIndex]
        for episodeIndex = 0 to season.episodes.Count() - 1
            if season.episodes[episodeIndex].id = id
                m.positions[seasonIndex.ToStr()] = episodeIndex
                m.seasons.jumpToItem = seasonIndex
                loadSeason(seasonIndex)
                m.episodes.jumpToItem = episodeIndex
                return
            end if
        end for
    end for
end sub
