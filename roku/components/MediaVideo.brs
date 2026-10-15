' Handle transport keys on the focused Video component before they reach the scene.
' Unhandled keys keep Roku's native seeking, replay and player UI behavior.
sub init()
    m.heldTransportKey = ""
    m.nativeTransportKey = ""
    m.skipIntro = invalid
    m.skipTimer = invalid
    m.nextUp = invalid
    if Type(m.top) = "roSGNode"
        m.nextUp = m.top.FindNode("nextUp")
        m.top.ObserveField("content", "resetTransportKeys")
        initializeIntroControls()
    end if
end sub

function onKeyEvent(key as string, press as boolean) as boolean
    ' Video's native Back handling can consume the key after overlay focus returns.
    ' Send an explicit exit command to the scene instead of relying on bubbling.
    if key = "back" and press
        if m.nextUp <> invalid
            if m.nextUp.visible
                m.nextUp.dismissed++
                return true
            end if
        end if
        m.top.exitRequested++
        return true
    end if
    transport = key = "OK" or key = "play" or key = "pause" or key = "playonly"
    if not transport
        if key = "options" or key = "left" or key = "right" or key = "fastforward" or key = "rewind"
            if m.skipIntro <> invalid then expireSkipIntro()
            if press and m.nextUp <> invalid
                if m.nextUp.visible then m.nextUp.releasedFocus++
            end if
        end if
        return false
    end if
    if press and key <> "OK" and m.nextUp <> invalid
        if m.nextUp.visible then m.nextUp.releasedFocus++
    end if
    ' Once delegated, keep the whole down/repeat/up sequence with the native player.
    ' Confirming a seek can hide the timeline before key-up arrives.
    if m.nativeTransportKey = key
        if not press then m.nativeTransportKey = ""
        return false
    end if
    ' The firmware owns the selected timeline position. Do not issue resume here:
    ' that resumes the old position instead of committing its pending seek.
    bar = m.top.trickPlayBar
    if bar <> invalid
        if bar.visible
            if press then m.nativeTransportKey = key
            m.heldTransportKey = ""
            print "VIDEO: native timeline handles "; key; " press="; press
            return false
        end if
    end if
    if not press
        if m.heldTransportKey = key then m.heldTransportKey = ""
        return true
    end if
    ' Ignore repeats while a transport key is held: one press means one toggle.
    if m.heldTransportKey = key then return true
    m.heldTransportKey = key
    if key = "OK"
        if m.nextUp <> invalid
            if m.nextUp.visible
                m.nextUp.activated++
                return true
            end if
        end if
        if activateSkipIntro() then return true
    end if
    state = m.top.state
    if state = "playing" and key <> "playonly"
        print "VIDEO: pause requested by "; key
        m.top.control = "pause"
    else if state = "paused" and key <> "pause"
        print "VIDEO: resume requested by "; key
        m.top.control = "resume"
    end if
    return true
end function

sub resetTransportKeys()
    ' A title handoff may move focus before the previous OK key-up arrives.
    m.heldTransportKey = ""
    m.nativeTransportKey = ""
end sub
