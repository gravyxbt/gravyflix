sub init()
    m.front = m.top.FindNode("artA")
    m.back = m.top.FindNode("artB")
    m.title = m.top.FindNode("title")
    m.meta = m.top.FindNode("metadata")
    m.description = m.top.FindNode("description")
    m.playAction = m.top.FindNode("playAction")
    m.playRing = m.top.FindNode("playRing")
    m.timer = m.top.FindNode("artDelay")
    m.fade = m.top.FindNode("crossfade")
    m.fadeOut = m.top.FindNode("fadeOut")
    m.fadeIn = m.top.FindNode("fadeIn")
    m.wanted = m.front.uri
    m.pending = ""
    m.fading = false
    m.front.ObserveField("loadStatus", "onArtLoaded")
    m.back.ObserveField("loadStatus", "onArtLoaded")
    m.timer.ObserveField("fire", "requestArt")
    m.fade.ObserveField("state", "onFadeState")
    m.top.ObserveField("focusedChild", "onFocus")
end sub

sub onContent()
    content = m.top.content
    if content = invalid then return
    m.title.text = content.title
    m.meta.text = content.metadataLine
    m.description.text = content.description
    m.playAction.visible = content.movieData.stream_url <> invalid or content.movieData.kind = "show"
    m.top.FindNode("actionLabel").text = HomeActionLabel(content.movieData)
    ' Text changes immediately. Artwork waits briefly for rapid scrolling to settle.
    m.wanted = content.heroImage
    m.timer.control = "stop"
    m.timer.control = "start"
end sub

sub requestArt()
    if m.fading or m.wanted = m.front.uri then return
    m.pending = m.wanted
    m.back.opacity = 0
    if m.back.uri = m.pending and m.back.loadStatus = "ready"
        onArtLoaded()
    else
        m.back.uri = m.pending
    end if
end sub

sub onArtLoaded()
    if m.fading or m.pending = "" then return
    if m.back.uri <> m.pending or m.pending <> m.wanted then return
    if m.back.loadStatus = "failed"
        m.wanted = "pkg:/images/hero-fallback.png"
        requestArt()
    else if m.back.loadStatus = "ready"
        m.fading = true
        m.fadeOut.fieldToInterp = m.front.id + ".opacity"
        m.fadeIn.fieldToInterp = m.back.id + ".opacity"
        m.fade.control = "start"
    end if
end sub

sub onFadeState()
    if m.fade.state <> "stopped" or not m.fading then return
    oldFront = m.front
    m.front = m.back
    m.back = oldFront
    m.front.opacity = 1
    m.back.opacity = 0
    m.back.uri = ""
    m.pending = ""
    m.fading = false
    if m.wanted <> m.front.uri then requestArt()
end sub

sub onFocus()
    if m.top.HasFocus()
        m.playRing.opacity = 1
    else
        m.playRing.opacity = 0
    end if
end sub

function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    if key = "OK" and m.playAction.visible
        m.top.playRequested++
        return true
    else if key = "up"
        m.top.exitUp++
        return true
    else if key = "down"
        m.top.exitDown++
        return true
    end if
    return false
end function

sub refreshAction()
    if m.top.content <> invalid then m.top.FindNode("actionLabel").text = HomeActionLabel(m.top.content.movieData)
end sub
