sub Main()
    m.top = {state:"playing",control:"",trickPlayBar:{visible:false},exitRequested:0}
    init()
    check(onKeyEvent("OK", true), "OK handled")
    check(m.top.control = "pause", "OK pauses playing video")
    m.top.state = "paused"
    onKeyEvent("OK", true)
    check(m.top.control = "pause", "Held OK does not immediately resume")
    onKeyEvent("OK", false)
    onKeyEvent("OK", true)
    check(m.top.control = "resume", "Second OK resumes")
    onKeyEvent("OK", false)
    m.top.state = "playing"
    onKeyEvent("play", true)
    check(m.top.control = "pause", "Play/Pause pauses")
    onKeyEvent("play", false)
    m.top.state = "paused"
    onKeyEvent("play", true)
    check(m.top.control = "resume", "Play/Pause resumes")
    onKeyEvent("play", false)
    m.top.control = ""
    onKeyEvent("pause", true)
    check(m.top.control = "", "Pause-only does not resume")
    onKeyEvent("pause", false)
    onKeyEvent("playonly", true)
    check(m.top.control = "resume", "Play-only resumes")
    onKeyEvent("playonly", false)
    m.top.state = "playing"
    m.top.control = ""
    onKeyEvent("playonly", true)
    check(m.top.control = "", "Play-only does not pause")
    check(onKeyEvent("back", true), "Video Back sends an explicit exit command")
    check(m.top.exitRequested = 1, "Back is delivered even when native Video would consume it")
    check(not onKeyEvent("back", false), "Back release does not send a second command")
    check(m.top.exitRequested = 1, "Exactly one exit command per Back press")
    check(not onKeyEvent("right", true), "Native seeking preserved")
    check(not onKeyEvent("options", true), "Native Options preserved")
    ' Native seek confirmation must not be replaced with control=resume.
    init()
    m.top.state = "paused"
    m.top.control = ""
    m.top.trickPlayBar.visible = true
    check(not onKeyEvent("OK", true), "Timeline OK delegated to native seek handler")
    check(m.top.control = "", "Seek confirmation does not resume the old position")
    m.top.trickPlayBar.visible = false
    check(not onKeyEvent("OK", true), "Held confirmation remains native after bar hides")
    check(not onKeyEvent("OK", false), "Native seek receives matching key release")
    m.top.state = "playing"
    check(onKeyEvent("OK", true), "Normal OK restored after seek confirmation")
    check(m.top.control = "pause", "Normal playback can pause again")
    onKeyEvent("OK", false)
    m.top.state = "paused"
    m.top.control = ""
    m.top.trickPlayBar.visible = true
    check(not onKeyEvent("play", true), "Timeline Play/Pause delegated to native handler")
    check(m.top.control = "", "Timeline Play/Pause does not bypass pending seek")
    check(not onKeyEvent("play", false), "Native Play/Pause receives key release")
    m.top.trickPlayBar = invalid
    check(onKeyEvent("OK", true), "Missing timeline safely uses normal controls")
    check(m.top.control = "resume", "Normal paused playback resumes without timeline")
    ' Skip Intro is selected visually without stealing native player focus.
    init()
    m.top.state = "playing"
    m.top.position = 30
    m.top.duration = 1200
    m.top.intro = {start:30,end:65}
    m.top.trickPlayBar = {visible:false}
    m.skipIntro = {visible:false}
    m.skipTimer = {control:""}
    resetIntroControls()
    updateSkipIntro()
    check(m.skipIntro.visible and m.skipTimer.control = "start", "Intro shows button and starts ten-second timer")
    m.top.control = ""
    check(onKeyEvent("OK", true), "Skip OK consumed")
    check(m.top.seek = 65 and m.top.control = "", "Skip seeks to marker without toggling pause")
    m.top.seek = 0
    onKeyEvent("OK", true)
    check(m.top.seek = 0, "Held Skip OK cannot trigger again")
    onKeyEvent("OK", false)
    onKeyEvent("OK", true)
    check(m.top.control = "pause", "Following OK returns to pause")
    onKeyEvent("OK", false)
    resetIntroControls()
    updateSkipIntro()
    m.top.control = ""
    m.top.seek = 0
    m.top.trickPlayBar.visible = true
    check(not onKeyEvent("OK",true), "Timeline confirmation takes priority over Skip Intro")
    check(m.top.seek = 0 and m.top.control = "", "Timeline is not overridden by intro seek")
    onKeyEvent("OK",false)
    m.top.trickPlayBar.visible = false
    expireSkipIntro()
    check(not m.skipIntro.visible and m.skipIntroUsed, "Button expires without skipping")
    resetIntroControls()
    m.top.position = 45
    updateSkipIntro()
    check(not m.skipIntro.visible, "Late seek into intro does not show expired window")
    m.top.position = 65
    updateSkipIntro()
    check(not m.skipIntro.visible, "End of intro hides button")
    resetIntroControls()
    m.top.position = 30
    updateSkipIntro()
    onKeyEvent("right",true)
    check(not m.skipIntro.visible, "Native seek dismisses button")

    ' A visually selected countdown never takes focus from this player.
    init()
    m.top.state = "playing"
    m.top.control = ""
    m.top.exitRequested = 0
    m.top.trickPlayBar = {visible:false}
    m.nextUp = {visible:true,dismissed:0,activated:0,releasedFocus:0}
    check(onKeyEvent("back",true), "First Back dismisses the visible countdown in the Video handler")
    check(m.nextUp.dismissed = 1 and m.top.exitRequested = 0, "Countdown cancellation does not exit playback")
    m.nextUp.visible = false ' Controller hides it; no focus change is required.
    onKeyEvent("back",false)
    check(onKeyEvent("OK",true) and m.top.control = "pause", "OK can pause immediately after dismissal")
    onKeyEvent("OK",false)
    m.top.state = "paused"
    check(onKeyEvent("play",true) and m.top.control = "resume", "Play/Pause can resume after dismissal")
    onKeyEvent("play",false)
    check(not onKeyEvent("fastforward",true), "Fast-forward remains available after dismissal")
    check(not onKeyEvent("rewind",true), "Rewind remains available after dismissal")
    check(onKeyEvent("back",true) and m.top.exitRequested = 1, "Next Back can exit after dismissal")
    m.top.state = "playing"
    m.top.control = ""
    m.nextUp.visible = true
    check(onKeyEvent("OK",true) and m.nextUp.activated = 1, "Countdown OK starts next rather than pausing")
    onKeyEvent("OK",true)
    check(m.nextUp.activated = 1, "Held OK cannot activate next twice")
    onKeyEvent("OK",false)
    check(not onKeyEvent("right",true) and m.nextUp.releasedFocus = 1, "Seeking dismisses the visual countdown and remains native")
    resetTransportKeys()
    m.top.state = "playing"
    m.top.control = ""
    check(onKeyEvent("play",true) and m.top.control = "pause", "Pause still works while countdown is visible")
    check(m.nextUp.releasedFocus = 2, "Transport controls dismiss countdown without a focus handoff")
    resetTransportKeys()
    m.nextUp.visible = false
    m.top.control = ""
    check(onKeyEvent("OK",true) and m.top.control = "pause", "New title resets held keys so the first OK can pause")
    print "PASS: Video controls"
end sub

sub check(condition as boolean, message as string)
    if not condition
        print "FAIL: "; message
        stop
    end if
end sub
