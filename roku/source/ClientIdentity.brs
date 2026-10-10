function MediaClientId() as string
    registry = CreateObject("roRegistrySection", "Gravyflix")
    key = registry.Read("clientId")
    if key = ""
        key = CreateObject("roDeviceInfo").GetRandomUUID()
        registry.Write("clientId", key)
        registry.Flush()
    end if
    return key
end function
