sub Main()
    m.top = {state:"playing",control:"",trickPlayBar:{visible:false}}
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
    check(not onKeyEvent("back", true), "Back bubbles to existing scene handler")
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

    print "PASS: Video controls"
end sub

sub check(condition as boolean, message as string)
    if not condition
        print "FAIL: "; message
        stop
    end if
end sub
