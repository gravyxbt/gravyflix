' The Video keeps focus. Only a visible Skip Intro changes what OK does.
sub initializeIntroControls()
    m.skipIntro = m.top.FindNode("skipIntro")
    m.skipTimer = m.top.FindNode("skipTimer")
    m.skipTimer.ObserveField("fire", "expireSkipIntro")
    m.top.ObserveField("position", "updateSkipIntro")
    m.top.ObserveField("state", "updateSkipIntro")
    resetIntroControls()
end sub

sub resetIntroControls()
    m.skipIntroUsed = false
    m.skipIntroShown = false
    if m.skipIntro <> invalid then m.skipIntro.visible = false
    if m.skipTimer <> invalid then m.skipTimer.control = "stop"
end sub

sub expireSkipIntro()
    m.skipIntroUsed = true
    if m.skipIntro <> invalid then m.skipIntro.visible = false
end sub

sub updateSkipIntro()
    if m.skipIntro = invalid then return
    marker = m.top.intro
    if marker = invalid then return
    if marker.start = invalid or marker.end = invalid then return
    position = m.top.position
    if m.top.state <> "playing" or position < marker.start or position >= marker.end
        m.skipIntro.visible = false
        return
    end if
    bar = m.top.trickPlayBar
    if bar <> invalid
        if bar.visible
            m.skipIntro.visible = false
            return
        end if
    end if
    if m.skipIntroUsed then return
    ' Show once, only in the first ten seconds of this intro, never on a late seek.
    if position >= marker.start + 10
        m.skipIntro.visible = false
        return
    end if
    if not m.skipIntroShown
        m.skipIntroShown = true
        m.skipTimer.control = "start"
        print "INTRO: Skip Intro available, end="; marker.end
    end if
    m.skipIntro.visible = true
end sub

function activateSkipIntro() as boolean
    if m.skipIntro = invalid then return false
    if not m.skipIntro.visible or m.top.state <> "playing" then return false
    marker = m.top.intro
    if marker = invalid then return false
    if marker.end = invalid or marker.start = invalid then return false
    if m.top.position < marker.start or m.top.position >= marker.end then return false
    if m.top.duration > 0 and marker.end >= m.top.duration then return false
    expireSkipIntro()
    m.skipTimer.control = "stop"
    print "INTRO: skipping to "; marker.end
    m.top.seek = marker.end
    return true
end function
