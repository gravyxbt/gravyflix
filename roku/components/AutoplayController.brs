' MainScene playback orchestration; uses its existing preparation Task and Video.
sub initializeAutoplay()
    m.nextUp = m.video.FindNode("nextUp")
    m.nextUp.ObserveField("activated", "requestAutoplay")
    m.nextUp.ObserveField("dismissed", "cancelAutoplay")
    m.nextUp.ObserveField("releasedFocus", "releaseNextUpFocus")
    m.video.notificationInterval = 1
    m.video.ObserveField("position", "updateNextUp")
    resetAutoplay()
end sub

sub resetAutoplay()
    stopNextEpisodePreparation()
    m.autoplayCount = 0
    m.autoplayVisited = {}
    m.confirmingAutoplay = false
    m.queuedAutoplay = invalid
    m.nextItem = invalid
    m.autoplayCancelled = false
    hideNextUp()
end sub

sub hideNextUp()
    m.nextUp.visible = false
    m.nextUpShown = false
end sub

sub prepareAutoplayForSelection()
    m.autoplayVisited[AutoplayId(m.selected)] = true
    m.nextItem = NextAutoplayItem(m.selected, m.movies, m.autoplayVisited)
    m.autoplayCancelled = false
    m.nextUpReleased = false
    hideNextUp()
    if m.nextItem <> invalid
        m.nextUp.item = m.nextItem
        print "AUTOPLAY: next is "; AutoplayLabel(m.nextItem)
    end if
end sub

sub updateNextUp()
    if m.mode <> "video" or m.nextItem = invalid or m.autoplayCancelled then return
    if m.video.state <> "playing" and m.video.state <> "paused" then return
    duration = m.video.duration
    position = m.video.position
    if duration = invalid or position = invalid then return
    if duration <= 0 then return
    remaining = Int(duration - position + 0.999)
    if not MovieNextWindow(m.selected, duration, position)
        hideNextUp()
        m.nextUpReleased = false
        return
    end if
    if remaining < 0 then remaining = 0
    m.nextUp.remaining = remaining
    if not m.nextUpShown and not m.nextUpReleased and m.video.state = "playing"
        bar = m.video.trickPlayBar
        if bar <> invalid
            if bar.visible then return ' Never steal focus while the user is choosing a seek.
        end if
        m.nextUp.visible = true
        m.nextUpShown = true
        ' Visually selected, while Video retains native transport/seek focus.
        print "AUTOPLAY: countdown ready; video keeps focus"
    end if
end sub

sub releaseNextUpFocus()
    hideNextUp()
    m.nextUpReleased = true
    ' No focus handoff: the Video never gave up remote focus.
end sub

sub cancelAutoplay()
    stopNextEpisodePreparation()
    m.autoplayCancelled = true
    releaseNextUpFocus()
    print "AUTOPLAY: cancelled for this title"
end sub

sub requestAutoplay()
    if m.mode <> "video" or m.nextItem = invalid or m.autoplayCancelled then return
    hideNextUp()
    if AutoplayNeedsConfirmation(m.autoplayCount)
        m.confirmingAutoplay = true
        m.mode = "confirm"
        if m.video.state = "playing" then m.video.control = "pause"
        dialog = CreateObject("roSGNode", "Dialog")
        dialog.title = "Are you still watching?"
        dialog.message = "Three titles have started automatically." + Chr(10) + "Next: " + AutoplayLabel(m.nextItem)
        dialog.buttons = ["Yes, keep watching", "No, stop"]
        dialog.ObserveField("buttonSelected", "onAutoplayConfirmation")
        dialog.ObserveField("wasClosed", "onAutoplayPromptClosed")
        m.autoplayDialog = dialog
        m.top.dialog = dialog
        return
    end if
    beginAutoplayTransition()
end sub

sub onAutoplayConfirmation(event as object)
    if not m.confirmingAutoplay then return
    approved = event.GetData() = 0
    m.confirmingAutoplay = false
    m.autoplayDialog.close = true
    if approved
        m.autoplayCount = 0
        beginAutoplayTransition()
    else
        stopAutoplayPrompt()
    end if
end sub

sub onAutoplayPromptClosed()
    if not m.confirmingAutoplay then return
    m.confirmingAutoplay = false
    stopAutoplayPrompt()
end sub

sub stopAutoplayPrompt()
    m.autoplayCancelled = true
    m.mode = "details"
    m.video.control = "stop"
    showDetails()
end sub

sub beginAutoplayTransition()
    endHistory("next")
    m.queuedAutoplay = m.nextItem
    m.autoplayCount++
    m.mode = "transition"
    ' Prevent stale position/key state and release the previous cache heartbeat.
    hideNextUp()
    if m.playbackTask <> invalid
        m.playbackTask.cancelled = true
        m.playbackTask.UnobserveField("result")
        m.playbackTask.UnobserveField("statusText")
        m.playbackTask = invalid
    end if
    if m.video.state = "finished" or m.video.state = "stopped"
        launchQueuedAutoplay()
    else
        m.video.control = "stop"
    end if
end sub

sub launchQueuedAutoplay()
    item = m.queuedAutoplay
    if item = invalid then return
    m.queuedAutoplay = invalid
    m.video.visible = false
    m.fromShow = item.kind = "episode"
    print "AUTOPLAY: starting "; AutoplayLabel(item); " transition="; m.autoplayCount
    if m.fromShow then m.showBrowser.CallFunc("selectEpisodeId", item.id)
    openMovie(item)
    m.launchIntent = "autoplay"
    onPlay()
end sub
