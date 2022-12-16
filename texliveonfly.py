#!/usr/bin/env python

# default options; feel free to change!
defaultCompiler = "pdflatex"
defaultArguments = "-synctex=1 -interaction=nonstopmode"
defaultSpeechSetting = "never"

#
# texliveonfly.py (formerly lualatexonfly.py) - "Downloading on the fly"
#     (similar to miktex) for texlive.
#
# Given a .tex file, runs lualatex (by default) repeatedly, using error messages
#     to install missing packages.
#
#
# Version 1.2 ; October 4, 2011
#
# Written on Ubuntu 10.04 with TexLive 2011
# Python 2.6+ or 3
# Should work on Linux and OS X
#
# Copyright (C) 2011 Saitulaa Naranong
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/copyleft/gpl.html>.

import re, subprocess, os, time,  optparse, sys, shlex

scriptName = os.path.basename(__file__)     #the name of this script file
py3 = sys.version_info[0]  >= 3

#functions to support python3's usage of bytes in some places where 2 uses strings
tobytesifpy3 = lambda s = None  : s.encode() if py3 and s != None else s
frombytesifpy3 = lambda b = None : b.decode("UTF-8") if py3 and b != None else b

#version of Popen.communicate that always takes and returns strings
#regardless of py version
def communicateStr ( process,  s = None ):
    (a,b) = process.communicate( tobytesifpy3(s) )
    return ( frombytesifpy3(a), frombytesifpy3(b) )

subprocess.Popen.communicateStr = communicateStr

#global variables (necessary in py2; for py3 should use nonlocal)
installation_initialized = False
installing = False


def generateTLMGRFuncs(tlmgr, speaker, sudoFunc):
    #checks that tlmgr is installed, raises OSError otherwise
    #also checks whether we need to escalate permissions, using fake remove command
    process = subprocess.Popen( [ tlmgr,  "remove" ], stdin=subprocess.PIPE, stdout = subprocess.PIPE,  stderr=subprocess.PIPE  )
    (tlmgr_out,  tlmgr_err) = process.communicateStr()

    #does our default user have update permissions?
    default_permission = "don't have permission" not in tlmgr_err

    #always call on first update; updates tlmgr and checks permissions
    def initializeInstallation():
        updateInfo = "Updating tlmgr prior to installing packages\n(this is necessary to avoid complaints from itself)."
        print( scriptName + ": " + updateInfo)

        if default_permission:
            process = subprocess.Popen( [tlmgr,  "update",  "--self" ] )
            process.wait()
        else:
            print( "\n{0}: Default user doesn't have permission to modify the TeX Live distribution; upgrading to superuser for installation mode.\n".format(scriptName) )
            basicCommand = ''''{0}' update --self'''.format(tlmgr)
            sudoFunc( basicCommand, '''echo \\"This is {0}'s 'install packages on the fly' feature.\\n\\n{1}\\n\\" ; sudo {2}'''.format(scriptName, updateInfo, basicCommand ) )

    def installPackages(packages):
        if len(packages) == 0:
            return

        global installation_initialized
        if not installation_initialized:
            initializeInstallation()
            installation_initialized = True

        packagesString = " ".join(packages)
        print("{0}: Attempting to install LaTex package(s): {1}".format( scriptName, packagesString ) )

        if default_permission:
            process = subprocess.Popen( [ tlmgr,  "install"] + packages , stdin=subprocess.PIPE )
            process.wait()
        else:
            basicCommand = ''''{0}' install {1}'''.format(tlmgr,  packagesString)
            bashCommand='''echo \\"This is {0}'s 'install packages on the fly' feature.\\n\\nAttempting to install LaTeX package(s): {1} \\"
echo \\"(Some of them might not be real.)\\n\\"
sudo {2}'''.format(scriptName, packagesString, basicCommand)

            sudoFunc(basicCommand, bashCommand)

    #strictmatch requires an entire /file match in the search results
    def getSearchResults(preamble, term, strictMatch):
        fontOrFile =  "font" if "font" in preamble else "file"
        speaker("Searching for missing {0}: {1} ".format(fontOrFile, term))
        print( "{0}: Searching repositories for missing {1} {2}".format(scriptName, fontOrFile,  term) )

        process = subprocess.Popen([ tlmgr, "search", "--global", "--file", term], stdin=subprocess.PIPE, stdout = subprocess.PIPE, stderr=subprocess.PIPE )
        ( output ,  stderrdata ) = process.communicateStr()
        outList = output.split("\n")

        results = ["latex"]    #latex 'result' for removal later

        for line in outList:
            line = line.strip()
            if line.startswith(preamble) and (not strictMatch or line.endswith("/" + term)):
                #filters out the package in:
                #   texmf-dist/.../package/file
                #and adds it to packages
                results.append(line.split("/")[-2].strip())
                results.append(line.split("/")[-3].strip()) #occasionally the package is one more slash before

        results = list(set(results))    #removes duplicates
        results.remove("latex")     #removes most common fake result

        if len(results) == 0:
            speaker("File not found.")
            print("{0}: No results found for {1}".format( scriptName,  term ) )
        else:
            speaker("Installing.")

        return results

    def searchFilePackage(file):
        return getSearchResults("texmf-dist/", file, True)

    def searchFontPackage(font):
        font = re.sub(r"\((.*)\)", "", font)    #gets rid of parentheses
        results = getSearchResults("texmf-dist/fonts/", font , False)

        #allow for possibility of lowercase
        if len(results) == 0:
            return [] if font.islower() else searchFontPackage(font.lower())
        else:
            return results

    def searchAndInstall(searcher,  entry):
        installPackages(searcher(entry))
        return entry    #returns the entry just installed

    return ( lambda entry : searchAndInstall(searchFilePackage,  entry),  lambda entry : searchAndInstall(searchFontPackage,  entry) )

def generateCompiler(compiler, arguments, texDoc, exiter):
    def compileTexDoc():
        try:
            process = subprocess.Popen( [compiler] + shlex.split(arguments) + [texDoc], stdin=sys.stdin, stdout = subprocess.PIPE )
            return readFromProcess(process)
        except OSError:
            print( "{0}: Unable to start {1}; are you sure it is installed?{2}".format(scriptName, compiler,
                "  \n\n(Or run " + scriptName + " --help for info on how to choose a different compiler.)" if compiler == defaultCompiler else "" )
                )
            exiter(1)

    def readFromProcess(process):
        getProcessLine = lambda : frombytesifpy3(process.stdout.readline())

        output = ""
        line = getProcessLine()
        while line != '':
            output += line
            sys.stdout.write(line)
            line = getProcessLine()

        returnCode = None
        while returnCode == None:
            returnCode = process.poll()

        return (output, returnCode)

    return compileTexDoc

### MAIN PROGRAM ###

if __name__ == '__main__':
    # Parse command line
    parser = optparse.OptionParser(
        usage="\n\n\t%prog [options] file.tex\n\nUse option --help for more info.",
        description = 'This program downloads TeX Live packages "on the fly" while compiling .tex documents.  ' +
            'Some of its default options can be directly changed in {0}.  For example, the default compiler can be edited on line 4.'.format(scriptName) ,
        version='1.2',
        epilog = 'Copyright (C) 2011 Saitulaa Naranong.  This program comes with ABSOLUTELY NO WARRANTY; see the GNU General Public License v3 for more info.' ,
        conflict_handler='resolve'
    )

    parser.add_option('-h', '--help', action='help', help='print this help text and exit')
    parser.add_option('-c', '--compiler', dest='compiler', metavar='COMPILER',
        help='your LaTeX compiler; defaults to {0}'.format(defaultCompiler), default=defaultCompiler)
    parser.add_option('-a', '--arguments', dest='arguments', metavar='ARGS',
        help='arguments to pass to compiler; default is: "{0}"'.format(defaultArguments) , default=defaultArguments)
    parser.add_option('--texlive_bin', dest='texlive_bin', metavar='LOCATION',
        help='Custom location for the TeX Live bin folder', default="")
    parser.add_option('--terminal_only', action = "store_true" , dest='terminal_only', default=False,
        help="Forces us to assume we can run only in this terminal.  Permission escalators will appear here rather than graphically or in a new terminal.")
    parser.add_option('-s',  '--speech_when' , dest='speech_setting', metavar="OPTION",  default=defaultSpeechSetting ,
        help='Toggles speech-synthesized notifications (where supported).  OPTION can be "always", "never", "installing", "failed", or some combination.')
    parser.add_option('-f', '--fail_silently', action = "store_true" , dest='fail_silently',
        help="If tlmgr cannot be found, compile document anyway.", default=False)

    (options, args) = parser.parse_args()

    if len(args) == 0:
        parser.error( "{0}: You must specify a .tex file to compile.".format(scriptName) )

    texDoc = args[0]
    compiler_path = os.path.join( options.texlive_bin, options.compiler)

    (installSpeaker, exitScript) = generateSpeakerFuncs(options.speech_setting)
    compileTex = generateCompiler( compiler_path, options.arguments, texDoc, exitScript)

    #initializes tlmgr, responds if the program not found
    try:
        if sys.platform.startswith('win'):
            tlmgr_path = os.path.join(options.texlive_bin, "tlmgr.bat")
            (installFile,  installFont) = generateTLMGRFuncs(tlmgr_path,  installSpeaker,  generateSudoer(options.terminal_only))
        else:
            tlmgr_path = os.path.join(options.texlive_bin, "tlmgr")
            (installFile,  installFont) = generateTLMGRFuncs(tlmgr_path,  installSpeaker,  generateSudoer(options.terminal_only))
    except OSError:
        if options.fail_silently:
            (output, returnCode)  = compileTex()
            exitScript(returnCode)
        else:
            parser.error( "{0}: It appears {1} is not installed.  {2}".format(scriptName, tlmgr_path,
                "Are you sure you have TeX Live 2010 or later?" if tlmgr_path == "tlmgr" else "" ) )

    #loop constraints
    done = False
    previousFile = ""
    previousFontFile = ""
    previousFont =""

    #keeps running until all missing font/file errors are gone, or the same ones persist in all categories
    while not done:
        (output, returnCode)  = compileTex()

        #most reliable: searches for missing file
        filesSearch = re.findall(r"! LaTeX Error: File `([^`']*)' not found" , output) + re.findall(r"! I can't find file `([^`']*)'." , output)
        filesSearch = [ name for name in filesSearch if name != texDoc ]  #strips our .tex doc from list of files
        #next most reliable: infers filename from font error
        fontsFileSearch = [ name + ".tfm" for name in re.findall(r"! Font \\[^=]*=([^\s]*)\s", output) ]
        #brute force search for font name in files
        fontsSearch =  re.findall(r"! Font [^\n]*file\:([^\:\n]*)\:", output) + re.findall(r"! Font \\[^/]*/([^/]*)/", output)

        try:
            if len(filesSearch) > 0 and filesSearch[0] != previousFile:
                previousFile = installFile(filesSearch[0] )
            elif len(fontsFileSearch) > 0 and fontsFileSearch[0] != previousFontFile:
                previousFontFile = installFile(fontsFileSearch[0])
            elif len(fontsSearch) > 0 and fontsSearch[0] != previousFont:
                previousFont = installFont(fontsSearch[0])
            else:
                done = True
        except OSError:
            print("\n{0}: Unable to update; all privilege escalation attempts have failed!".format(scriptName) )
            print("We've already compiled the .tex document, so there's nothing else to do.\n  Exiting..")
            exitScript(returnCode)

    exitScript(returnCode)
