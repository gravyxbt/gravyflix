sub init()
    m.top.backgroundColor = "0x0B1220FF"
    m.top.backgroundUri = ""
    for each id in ["library", "details", "poster", "movieTitle", "movieInfo", "play", "video", "showBrowser"]
        m[id] = m.top.FindNode(id)
    end for
    observeTitleActions()
    m.library.ObserveField("refreshRequested", "refreshLibrary")
    m.play.ObserveField("buttonSelected", "onPlay")
    m.video.ObserveField("state", "onVideoState")
    initializeAutoplay()
    initializeHistory()
    m.fromShow = false
    m.mode = "library"
    m.loading = false
    m.movies = []
    m.top.SetFocus(true)
    loadMovies()
end sub

sub observeTitleActions()
    ' Navigation observes explicit user commands, never mutable cached payloads.
    m.library.ObserveField("titleRequested", "onSelected")
    m.library.ObserveField("playRequested", "onHeroPlay")
    m.showBrowser.ObserveField("episodeRequested", "onEpisodeSelected")
end sub

sub refreshLibrary()
    loadMovies(true)
end sub

sub loadMovies(rescan = false as boolean, preserveLibrary = false as boolean)
    if m.loading then return
    m.loading = true
    m.preserveLibrary = preserveLibrary
    if not preserveLibrary then m.library.statusText = "Loading your library..."
    m.task = CreateObject("roSGNode", "ApiTask")
    m.task.url = ServerUrl() + "/api/library/browse"
    if rescan
        m.library.statusText = "Scanning for new movies and episodes..."
        m.task.scanUrl = ServerUrl() + "/api/library/scan"
    end if
    m.task.ObserveField("result", "onMovies")
    m.task.control = "RUN"
end sub

sub onMovies()
    m.loading = false
    result = m.task.result
    if result.error <> invalid
        if m.preserveLibrary
            print "API: background library update failed: "; result.error
            return
        end if
        m.library.statusText = "Unable to refresh the media library." + Chr(10) + "Server: " + ServerUrl() + Chr(10) + result.error + Chr(10) + "Press OK to retry."
        return
    end if
    m.movies = result.movies
    if m.preserveLibrary
        m.library.CallFunc("updateCachedMovies", m.movies)
    else
        m.library.movies = m.movies
    end if
end sub

function posterFor(movie as object) as string
    if movie.poster_url <> invalid
        if movie.poster_url <> "" then return movie.poster_url
    end if
    return "pkg:/images/default-poster.png"
end function

sub onSelected()
    if m.mode <> "library" or not m.library.visible then return
    openTitle(m.library.selectedMovie)
end sub

sub onHeroPlay()
    if m.mode <> "library" or not m.library.visible then return
    item = m.library.playMovie
    if item = invalid then return
    target = HomeResumeTarget(item)
    if item.kind = "show" and target <> invalid
        resetAutoplay()
        m.fromShow = true
        m.showBrowser.showData = item
        openMovie(target)
    else
        openTitle(item)
    end if
    if m.mode = "details" then onPlay()
end sub

sub openTitle(item as object)
    if item = invalid then return
    resetAutoplay()
    m.fromShow = false
    if item.kind = "show"
        m.library.visible = false
        m.showBrowser.showData = item
        m.showBrowser.visible = true
        m.mode = "show"
        m.showBrowser.CallFunc("focusBrowser")
    else
        openMovie(item)
    end if
end sub

sub onEpisodeSelected()
    if m.mode <> "show" or not m.showBrowser.visible then return
    resetAutoplay()
    m.fromShow = true
    m.showBrowser.visible = false
    openMovie(m.showBrowser.selectedEpisode)
end sub

sub openMovie(movie as object)
    if movie = invalid then return
    m.launchIntent = "resume"
    m.compatibleRetry = false
    m.retryUsed = false
    m.fallbackResume = 0
    m.audioOriginal = false
    m.selected = movie
    print "UI: selected movie id "; m.selected.id
    m.poster.uri = posterFor(m.selected)
    m.movieTitle.text = m.selected.title
    if m.fromShow then m.movieTitle.text = m.selected.show_title + " · " + m.selected.title
    info = TitleSummary(m.selected)
    m.top.FindNode("titleMetadata").text = MoviePresentation(m.selected).metadataLine
    m.top.FindNode("titleCast").text = TitleCast(m.selected)
    print "UI: title file="; m.selected.filename; " compatibility="; m.selected.compatibility_note
    m.top.FindNode("backHint").text = "Back  Movies"
    if m.fromShow then m.top.FindNode("backHint").text = "Back  Episodes"
    m.play.text = "Play"
    if movie.resume_position <> invalid and movie.resume_position > 15 then m.play.text = "Resume"
    m.top.FindNode("restart").visible = m.play.text = "Resume"
    m.detailsInfo = info
    m.movieInfo.text = info
    m.top.FindNode("audioHint").visible = true
    updateAudioHint()
    m.library.visible = false
    m.details.visible = true
    m.mode = "details"
    m.play.SetFocus(true)
    loadCaptionIndicator()
end sub

function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    if m.mode = "details" and m.top.FindNode("restart").visible
        if key = "right" and m.play.HasFocus()
            m.top.FindNode("restart").SetFocus(true)
            return true
        else if key = "left" and m.top.FindNode("restart").HasFocus()
            m.play.SetFocus(true)
            return true
        end if
    end if
    if key = "options" and m.mode = "details"
        showPlaybackOptions()
        return true
    end if
    if key = "back" and m.mode = "preparing"
        showDetails()
        return true
    end if
    if key = "back" and m.mode = "video"
        endHistory("stopped")
        m.video.control = "stop"
        showDetails()
        return true
    end if
    if key = "back" and m.mode = "show"
        m.showBrowser.visible = false
        m.library.visible = true
        m.mode = "library"
        m.library.CallFunc("focusHome")
        loadMovies(false, true)
        return true
    end if
    if key = "back" and m.mode = "details" and m.fromShow
        m.details.visible = false
        m.showBrowser.visible = true
        m.mode = "show"
        m.showBrowser.CallFunc("focusEpisodes")
        return true
    end if
    if key = "back" and m.mode = "details"
        m.details.visible = false
        m.library.visible = true
        m.mode = "library"
        m.library.CallFunc("focusHome")
        loadMovies(false, true)
        return true
    end if
    return false
end function

sub onPlay()
    if m.mode <> "details" then return
    cancelCaptionIndicator()
    m.mode = "preparing"
    m.movieInfo.text = "Checking playback compatibility..." + Chr(10) + "Back cancels."
    m.top.SetFocus(true)
    m.playbackTask = CreateObject("roSGNode", "PlaybackTask")
    m.playbackTask.baseUrl = ServerUrl()
    m.playbackTask.movieId = m.selected.id
    m.playbackTask.intent = m.launchIntent
    if m.audioOriginal then m.playbackTask.mode = "original"
    if m.compatibleRetry then m.playbackTask.mode = "compatible"
    m.playbackTask.ObserveField("statusText", "onAudioStatus")
    m.playbackTask.ObserveField("result", "onAudioReady")
    m.playbackTask.control = "RUN"
end sub

function needsPreparation() as boolean
    if isMkv() then return true
    if m.selected = invalid then return false
    if m.selected.filename = invalid then return false
    return LCase(Right(m.selected.filename, 4)) = ".avi"
end function

function isMkv() as boolean
    if m.selected = invalid then return false
    if m.selected.filename = invalid then return false
    return LCase(Right(m.selected.filename, 4)) = ".mkv"
end function

sub updateAudioHint()
    text = "Playback: Automatic  |  * Options to change"
    if m.compatibleRetry then text = "Playback: Compatible H.264/AAC  |  * Options to change"
    if m.audioOriginal then text = "Playback: Original file  |  * Options to change"
    m.top.FindNode("audioHint").text = text
end sub

sub onAudioStatus(event as object)
    if m.mode <> "preparing" then return
    if m.playbackTask = invalid then return
    if event.GetRoSGNode().IsSameNode(m.playbackTask) then m.movieInfo.text = event.GetData()
end sub

sub onAudioReady(event as object)
    if m.mode <> "preparing" then return
    if m.playbackTask = invalid then return
    if not event.GetRoSGNode().IsSameNode(m.playbackTask) then return
    plan = event.GetData()
    if plan.error <> invalid
        showDetails()
        m.movieInfo.text = plan.error + Chr(10) + "Press Play to retry."
        m.movieInfo.text += " Press * to choose a playback mode."
        return
    end if
    startVideo(plan)
end sub

sub onSubtitlesReady(event as object)
    if m.mode <> "preparing" or m.subtitleTask = invalid then return
    if not event.GetRoSGNode().IsSameNode(m.subtitleTask) then return
    plan = {stream_url: m.selected.stream_url, stream_format: m.selected.stream_format}
    data = event.GetData()
    if data.tracks <> invalid then plan.subtitle_tracks = data.tracks
    if data.intro <> invalid then plan.intro = data.intro
    if data.credits_start <> invalid then plan.credits_start = data.credits_start
    m.subtitleTask.UnobserveField("result")
    m.subtitleTask = invalid
    startVideo(plan)
end sub

sub startVideo(plan as object)
    content = CreateObject("roSGNode", "ContentNode")
    content.title = m.selected.title
    content.url = plan.stream_url
    content.streamFormat = "mp4"
    if plan.stream_format <> invalid then content.streamFormat = plan.stream_format
    if m.selected.duration <> invalid then content.length = m.selected.duration
    print "VIDEO: starting "; content.url; " format="; content.streamFormat
    tracks = []
    if plan.subtitle_tracks <> invalid
        for each caption in plan.subtitle_tracks
            tracks.Push({Language: caption.language, Description: caption.description, TrackName: caption.url})
        end for
    end if
    content.SubtitleTracks = tracks
    print "SUBTITLE: attached "; tracks.Count(); " tracks; Options (*) changes captions"
    ' The new foreground lease is already acquired: release the old lookahead now.
    stopNextEpisodePreparation()
    m.selected.credits_start = invalid
    if plan.credits_start <> invalid then m.selected.credits_start = plan.credits_start
    prepareAutoplayForSelection()
    m.video.intro = {}
    if plan.intro <> invalid then m.video.intro = plan.intro
    m.video.content = content
    m.mode = "video"
    m.details.visible = false
    m.video.visible = true
    m.video.SetFocus(true)
    m.currentDelivery = plan.delivery
    beginHistory(plan)
    if m.fallbackResume > 0
        m.resumePending = m.fallbackResume
        m.fallbackResume = 0
    end if
    m.video.control = "play"
end sub

sub showDetails()
    stopNextEpisodePreparation()
    hideNextUp()
    cancelCaptionIndicator()
    if m.subtitleTask <> invalid
        m.subtitleTask.cancelled = true
        m.subtitleTask.UnobserveField("result")
        m.subtitleTask = invalid
    end if
    if m.playbackTask <> invalid
        m.playbackTask.cancelled = true
        m.playbackTask.UnobserveField("result")
        m.playbackTask.UnobserveField("statusText")
        m.playbackTask = invalid
    end if
    m.movieInfo.text = m.detailsInfo
    m.video.visible = false
    m.details.visible = true
    m.mode = "details"
    m.play.SetFocus(true)
end sub

sub onVideoState()
    state = m.video.state
    historyState(state)
    print "VIDEO: state "; state
    if m.mode = "transition"
        if state = "stopped" then launchQueuedAutoplay()
        return
    end if
    if m.mode <> "video" then return
    if state = "playing"
        updateNextUp()
        startNextEpisodePreparation()
    end if
    if state = "error"
        print "VIDEO ERROR: code="; m.video.errorCode; " message="; m.video.errorMsg
        print "VIDEO ERROR: "; m.video.errorStr
        print "VIDEO ERROR: info="; FormatJson(m.video.errorInfo)
        if m.video.errorCode = -5 and not m.retryUsed and not m.audioOriginal and m.currentDelivery <> "video_convert"
            m.fallbackResume = m.historyPosition
            m.retryUsed = true
            m.compatibleRetry = true
            showDetails()
            print "VIDEO: one compatible retry after decoder failure"
            onPlay()
            return
        end if
        showDetails()
        m.movieInfo.text = "Playback failed (" + m.video.errorCode.ToStr() + ")." + Chr(10) + m.video.errorMsg + Chr(10) + "Check server and Roku logs. This file may need conversion to H.264/AAC MP4."
    else if state = "finished"
        if m.nextItem <> invalid and not m.autoplayCancelled
            requestAutoplay()
        else
            showDetails()
        end if
    else if state = "stopped"
        showDetails()
    end if
end sub

sub cancelCaptionIndicator()
    if m.captionInfoTask <> invalid
        m.captionInfoTask.cancelled = true
        m.captionInfoTask.UnobserveField("result")
        m.captionInfoTask = invalid
    end if
end sub

sub loadCaptionIndicator()
    cancelCaptionIndicator()
    m.top.FindNode("subtitleHint").text = SubtitleIndicatorLabel(m.selected.subtitle_summary)
    m.captionInfoTask = CreateObject("roSGNode", "SubtitleTask")
    m.captionInfoTask.baseUrl = ServerUrl()
    m.captionInfoTask.movieId = m.selected.id
    m.captionInfoTask.ObserveField("result", "onCaptionIndicator")
    m.captionInfoTask.control = "RUN"
end sub

sub onCaptionIndicator(event as object)
    if m.mode <> "details" or m.captionInfoTask = invalid then return
    if not event.GetRoSGNode().IsSameNode(m.captionInfoTask) then return
    data = event.GetData()
    if data.error = invalid
        m.top.FindNode("subtitleHint").text = SubtitleIndicatorLabel(SubtitleSummaryFromTracks(data))
    end if
    cancelCaptionIndicator()
end sub

sub showPlaybackOptions()
    dialog = CreateObject("roSGNode", "Dialog")
    dialog.title = "Playback mode"
    dialog.message = "Automatic uses the file and device capabilities. Compatible prepares H.264/AAC. Original depends on your device."
    dialog.buttons = ["Automatic", "Compatible H.264/AAC", "Original file"]
    dialog.ObserveField("buttonSelected", "onPlaybackOption")
    dialog.ObserveField("wasClosed", "onPlaybackOptionsClosed")
    m.playbackDialog = dialog
    m.top.dialog = dialog
end sub

sub onPlaybackOption(event as object)
    choice = event.GetData()
    m.audioOriginal = choice = 2
    m.compatibleRetry = choice = 1
    m.retryUsed = false
    updateAudioHint()
    m.playbackDialog.close = true
end sub

sub onPlaybackOptionsClosed()
    m.playbackDialog = invalid
    if m.mode = "details" then m.play.SetFocus(true)
end sub
