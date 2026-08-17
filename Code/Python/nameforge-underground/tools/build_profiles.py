#!/usr/bin/env python3
"""Generates the enriched NameForge profile/lexicon JSON files.

Kept in the repo so the vocabulary stays reviewable as data rather than as a
900-line JSON blob edited by hand.

Term tuple: (term, gloss, tags, since, until, weight, register)
register: insider | common | pop
"""
import json
from pathlib import Path

D = 9999  # "still current"


def T(term, gloss, tags, since=1970, until=D, weight=1.0, register="common"):
    e = {"term": term, "tags": list(tags), "gloss": gloss}
    if since != 1970:
        e["since"] = since
    if until != D:
        e["until"] = until
    if weight != 1.0:
        e["weight"] = weight
    if register != "common":
        e["register"] = register
    return e


# ---------------------------------------------------------------------------
# TECHNICAL — the machine itself. Reads as competence, not costume.
# ---------------------------------------------------------------------------
TECHNICAL = [
    T("opcode", "a single machine instruction", ["technical", "lowlevel"], 1975, weight=1.3, register="insider"),
    T("stack", "the call stack; also what you smash", ["technical", "lowlevel"], 1970, weight=1.2),
    T("heap", "dynamically allocated memory", ["technical", "lowlevel"], 1975, register="insider"),
    T("daemon", "a background process; the old spelling of demon", ["technical", "mythological"], 1975, weight=1.3, register="insider"),
    T("kernel", "the core of the operating system", ["technical", "lowlevel"], 1975, weight=1.2),
    T("segfault", "a memory access violation; failure as identity", ["technical", "lowlevel", "irreverent"], 1985, weight=1.2, register="insider"),
    T("overflow", "writing past the end of a buffer", ["technical", "lowlevel"], 1980, weight=1.2),
    T("underflow", "arithmetic falling below representable range", ["technical", "lowlevel"], 1980, register="insider"),
    T("syscall", "a request from userland into the kernel", ["technical", "lowlevel"], 1985, register="insider"),
    T("register", "a slot inside the processor itself", ["technical", "lowlevel"], 1975, register="insider"),
    T("offset", "a distance from a base address", ["technical", "lowlevel"], 1975),
    T("pointer", "an address standing in for a thing", ["technical", "lowlevel", "abstract"], 1975),
    T("nullptr", "the pointer that refers to nothing", ["technical", "abstract"], 1990, register="insider"),
    T("buffer", "the space between input and disaster", ["technical", "lowlevel"], 1975),
    T("packet", "the unit of everything that moves", ["technical", "network"], 1970, weight=1.2),
    T("socket", "an endpoint of a connection", ["technical", "network"], 1982),
    T("inode", "the filesystem's real name for a file", ["technical", "lowlevel"], 1975, register="insider"),
    T("sigkill", "the signal that cannot be caught or ignored", ["technical", "threatening"], 1985, weight=1.2, register="insider"),
    T("sigint", "the interrupt signal; also a pun on intelligence work", ["technical", "cryptographic"], 1985, register="insider"),
    T("ptrace", "the syscall that lets one process watch another", ["technical", "surveillance"], 1985, register="insider"),
    T("strace", "the tool that prints what a program really does", ["technical"], 1992, register="insider"),
    T("coredump", "the corpse a crashed program leaves behind", ["technical", "macabre"], 1980, weight=1.2, register="insider"),
    T("deadlock", "two processes each waiting for the other forever", ["technical", "abstract"], 1975, weight=1.3),
    T("racecond", "a bug that depends on who arrives first", ["technical"], 1985, register="insider"),
    T("mutex", "the lock that guarantees only one", ["technical", "minimal"], 1985, register="insider"),
    T("semaphore", "a signal flag, at sea and in memory", ["technical", "abstract"], 1975, weight=1.1),
    T("fork", "the call that splits a process in two", ["technical", "minimal"], 1975, weight=1.2),
    T("pipe", "output of one thing as input to the next", ["technical", "minimal"], 1975),
    T("shim", "a thin layer that makes two things fit", ["technical", "irreverent"], 1990),
    T("stub", "a placeholder that pretends to be the real thing", ["technical", "abstract"], 1980),
    T("hook", "code that intercepts something on its way past", ["technical", "surveillance"], 1985, weight=1.2),
    T("payload", "the part that actually does something", ["technical", "threatening"], 1985),
    T("loader", "the thing that puts code where it runs", ["technical"], 1980),
    T("bootstrap", "pulling yourself up by your own bootloader", ["technical", "abstract"], 1975),
    T("firmware", "software that thinks it is hardware", ["technical", "lowlevel"], 1980),
    T("bytecode", "instructions for a machine that does not exist", ["technical", "abstract"], 1985, register="insider"),
    T("checksum", "a small number that proves a large one", ["technical", "cryptographic"], 1975),
    T("parity", "the bit that tells you something went wrong", ["technical", "abstract"], 1970),
    T("latency", "the delay you cannot engineer away", ["technical", "abstract"], 1980, weight=1.1),
    T("jitter", "variation in delay; nervousness as a metric", ["technical", "abstract"], 1985),
    T("bitrot", "data decaying quietly where nobody looks", ["technical", "organic", "abstract"], 1985, weight=1.3, register="insider"),
    T("endian", "which end of a number comes first; a war of taste", ["technical", "irreverent"], 1980, register="insider"),
    T("hexdump", "the raw bytes, printed for humans", ["technical", "lowlevel"], 1980, register="insider"),
    T("scratch", "temporary space nobody backs up", ["technical", "mundane"], 1975),
    T("spool", "the queue nothing ever leaves on time", ["technical", "bureaucratic"], 1975),
    T("cronjob", "a task that runs whether anyone is watching or not", ["technical", "mundane"], 1980, register="insider"),
    T("chroot", "a cage a process cannot see out of", ["technical", "threatening"], 1985, register="insider"),
    T("symlink", "a name pointing at another name", ["technical", "abstract"], 1985, register="insider"),
    T("umask", "what a new file is not allowed to be", ["technical", "cryptographic"], 1980, register="insider"),
    T("trapdoor", "a way in that was left on purpose", ["technical", "threatening"], 1980, weight=1.2),
    T("kludge", "a fix that works and should not", ["technical", "irreverent", "oldschool"], 1975, weight=1.2, register="insider"),
    T("bogon", "a unit of bogosity; a packet that should not exist", ["technical", "irreverent", "oldschool"], 1980, weight=1.2, register="insider"),
    T("frob", "to adjust something with no idea of the units", ["technical", "irreverent", "oldschool"], 1975, register="insider"),
    T("grep", "to search; used as a verb for thinking", ["technical", "minimal"], 1975, weight=1.1),
    T("nybble", "half a byte, spelled for the joke", ["technical", "irreverent"], 1975, register="insider"),
    T("quine", "a program whose only output is itself", ["technical", "literary", "abstract"], 1980, weight=1.2, register="insider"),
    T("nulldev", "the device that accepts everything and keeps nothing", ["technical", "abstract"], 1975, register="insider"),
    T("null", "the value that means: deliberately nothing", ["technical", "abstract", "minimal"], 1970, weight=1.3),
    T("root", "total authority, named after a directory", ["technical", "minimal"], 1975, weight=1.2),
    T("core", "memory, back when it was physically wound", ["technical", "oldschool", "minimal"], 1970, weight=1.2),
    T("zero", "the number that had to be argued for", ["technical", "abstract", "minimal"], 1970),
    T("watchdog", "the timer that reboots you if you go quiet", ["technical", "surveillance"], 1980),
    T("heartbeat", "the packet that only means: still here", ["technical", "organic", "abstract"], 1985, weight=1.1),
]

# ---------------------------------------------------------------------------
# CRYPTO — cypherpunk register. Privacy, proof, paranoia.
# ---------------------------------------------------------------------------
CRYPTO = [
    T("cipher", "a system for making meaning unreadable", ["cryptographic", "abstract"], 1970, weight=1.3),
    T("nonce", "a number used exactly once, then never again", ["cryptographic", "minimal"], 1980, weight=1.3, register="insider"),
    T("saltbyte", "the randomness that makes two identical secrets differ", ["cryptographic"], 1985, register="insider"),
    T("keyring", "the collection of who you are willing to trust", ["cryptographic", "mundane"], 1991, weight=1.2),
    T("fingerprint", "a short proof of a long key", ["cryptographic", "surveillance"], 1991),
    T("plaintext", "the dangerous version", ["cryptographic", "minimal"], 1975, weight=1.2),
    T("ciphertext", "the safe version nobody can read", ["cryptographic"], 1975),
    T("onerway", "a function easy forward and hopeless backward", ["cryptographic", "abstract"], 1980, register="insider"),
    T("padding", "meaningless bytes that hide the shape of meaning", ["cryptographic", "abstract"], 1980),
    T("remailer", "a relay that forgets where mail came from", ["cryptographic", "oldschool"], 1992, 2010, weight=1.2, register="insider"),
    T("deniable", "encryption you can honestly claim is not there", ["cryptographic", "abstract"], 1997, weight=1.2),
    T("passphrase", "the sentence standing between them and everything", ["cryptographic", "mundane"], 1991),
    T("entropybit", "the raw unpredictability everything else rests on", ["cryptographic", "abstract"], 1985, register="insider"),
    T("tempest", "leakage of secrets through stray emissions", ["cryptographic", "surveillance", "threatening"], 1975, weight=1.2, register="insider"),
    T("blinding", "hiding the input even from the one computing it", ["cryptographic", "abstract"], 1983, register="insider"),
    T("shamir", "the shared secret that needs several people to open", ["cryptographic", "literary"], 1979, register="insider"),
    T("dropbox", "a place to leave something without meeting", ["cryptographic", "mundane", "threatening"], 1975, weight=1.1),
    T("burnbag", "the container for what must not survive the day", ["cryptographic", "threatening", "mundane"], 1975, register="insider"),
    T("coldkey", "a key kept away from any network, on purpose", ["cryptographic", "minimal"], 1995),
    T("nullkey", "a key that decrypts nothing; a deliberate dead end", ["cryptographic", "abstract"], 1985, register="insider"),
]

# ---------------------------------------------------------------------------
# ABSTRACT — says almost nothing, which is the point.
# ---------------------------------------------------------------------------
ABSTRACT = [
    T("entropy", "the tendency of order to leave", ["abstract", "scientific"], 1970, weight=1.4),
    T("void", "the absence that has a name", ["abstract", "minimal"], 1970, weight=1.2),
    T("absence", "the shape left by something removed", ["abstract", "literary"], 1970),
    T("static", "noise that sounds like a signal from far away", ["abstract"], 1970, weight=1.2),
    T("noise", "everything you did not mean to send", ["abstract", "minimal"], 1970),
    T("paradox", "the statement that undoes itself", ["abstract", "literary"], 1970),
    T("silence", "the answer that cannot be quoted", ["abstract", "literary"], 1970),
    T("afterimage", "what stays behind the eyelids", ["abstract", "literary"], 1970, weight=1.2),
    T("nadir", "the lowest point, named precisely", ["abstract", "literary", "minimal"], 1970, weight=1.1),
    T("axiom", "the thing assumed so everything else can follow", ["abstract", "literary"], 1970, weight=1.2),
    T("anomaly", "the data point nobody can explain away", ["abstract", "scientific"], 1970),
    T("riddle", "a question shaped like an insult", ["abstract", "literary"], 1970),
    T("oblivion", "being forgotten, considered as a destination", ["abstract", "gothic"], 1970),
    T("fracture", "the line along which something will break", ["abstract", "gothic"], 1970),
    T("delta", "the difference between two states", ["abstract", "scientific", "minimal"], 1970, weight=1.1),
    T("asymptote", "approaching forever and never arriving", ["abstract", "scientific", "literary"], 1970, weight=1.2),
    T("halflife", "the time it takes for half of it to be gone", ["abstract", "scientific"], 1970, weight=1.2),
    T("penumbra", "the partial shadow at the edge of the full one", ["abstract", "literary", "gothic"], 1970, weight=1.2),
    T("interval", "the gap that is also a measurement", ["abstract", "minimal"], 1970),
    T("residue", "what is left after the reaction finishes", ["abstract", "organic"], 1970, weight=1.1),
    T("threshold", "the point at which behaviour changes", ["abstract", "scientific"], 1970),
    T("attractor", "the state a system keeps falling back into", ["abstract", "scientific"], 1980, weight=1.1, register="insider"),
    T("aporia", "the impasse where reasoning stops", ["abstract", "literary"], 1970, register="insider"),
    T("lacuna", "a gap in a manuscript where text is missing", ["abstract", "literary"], 1970, weight=1.2, register="insider"),
    T("umbra", "the total shadow, where nothing gets through", ["abstract", "gothic", "minimal"], 1970),
    T("vestige", "the trace of something no longer functional", ["abstract", "organic"], 1970),
    T("erratum", "the printed correction of a printed mistake", ["abstract", "bureaucratic", "literary"], 1970, weight=1.1),
    T("quietus", "a final settling; a discharge from obligation", ["abstract", "gothic", "literary"], 1970, register="insider"),
]

# ---------------------------------------------------------------------------
# MYTHOLOGY — public-domain, no modern IP.
# ---------------------------------------------------------------------------
MYTH = [
    T("loki", "the trickster who is useful right up until he is not", ["mythological", "irreverent"], 1970, weight=1.2),
    T("hermes", "messenger, and patron of thieves", ["mythological", "network"], 1970, weight=1.2),
    T("anubis", "the one who weighs what you were", ["mythological", "gothic"], 1970),
    T("janus", "two faces, one head", ["mythological", "literary"], 1970, weight=1.3),
    T("icarus", "the cautionary tale everyone thinks is about someone else", ["mythological", "literary"], 1970),
    T("morpheus", "shaper of dreams", ["mythological", "literary"], 1970, weight=0.8, register="pop"),
    T("orpheus", "the one who looked back", ["mythological", "literary", "gothic"], 1970, weight=1.2),
    T("nyx", "primordial night; short and unimprovable", ["mythological", "gothic", "minimal"], 1970, weight=1.3),
    T("eris", "discord, and the apple that started it", ["mythological", "irreverent"], 1970, weight=1.2),
    T("hecate", "goddess of crossroads and things done at night", ["mythological", "gothic"], 1970),
    T("charon", "the ferryman who requires payment", ["mythological", "gothic"], 1970, weight=1.2),
    T("prometheus", "punished specifically for sharing", ["mythological", "literary"], 1970),
    T("cassandra", "right every time, believed never", ["mythological", "literary"], 1970, weight=1.3),
    T("sisyphus", "the patron saint of maintenance work", ["mythological", "irreverent", "literary"], 1970, weight=1.2),
    T("argus", "the watchman with a hundred eyes", ["mythological", "surveillance"], 1970, weight=1.2),
    T("mnemosyne", "memory, personified and inconveniently long", ["mythological", "literary"], 1970, weight=0.8),
    T("lethe", "the river of forgetting", ["mythological", "gothic", "minimal"], 1970, weight=1.3),
    T("thoth", "scribe of the gods; keeper of records", ["mythological", "bureaucratic"], 1970, weight=1.1),
    T("golem", "a made thing that follows instructions too exactly", ["mythological", "literary"], 1970, weight=1.2),
    T("banshee", "the one whose arrival is the message", ["mythological", "gothic", "threatening"], 1970),
    T("wyrm", "the older spelling of the older monster", ["mythological", "gothic", "oldschool"], 1970, weight=1.2),
    T("kraken", "the thing that is only ever released", ["mythological", "threatening"], 1970, weight=0.9),
    T("nemesis", "retribution as a personality", ["mythological", "threatening"], 1970, weight=0.9),
    T("oracle", "answers that are technically correct", ["mythological", "literary", "technical"], 1970, weight=1.2),
    T("chimera", "several animals arguing inside one body", ["mythological", "literary"], 1970, weight=1.1),
    T("moirai", "the three who measure and cut the thread", ["mythological", "gothic"], 1970, register="insider"),
]

# ---------------------------------------------------------------------------
# SCIFI — genre texture without borrowing anyone's characters.
# 2.0 shipped proper nouns lifted straight from published novels and films;
# using those as a character's alias is an avoidable originality problem.
# ---------------------------------------------------------------------------
SCIFI = [
    T("sprawl", "unplanned urban growth, extended to the horizon", ["cyberpunk", "literary"], 1984, weight=1.2),
    T("arcology", "a city that is one building", ["cyberpunk", "literary"], 1970, weight=1.2),
    T("offworld", "anywhere that is not here", ["cyberpunk", "literary"], 1975),
    T("coldsleep", "the long unconsciousness between places", ["literary", "gothic"], 1970, weight=1.2),
    T("terraform", "editing a planet until it is survivable", ["literary", "scientific"], 1970),
    T("lagrange", "a point where the forces cancel and you can rest", ["scientific", "literary"], 1970, weight=1.2),
    T("sublight", "slower than the thing everyone wants to beat", ["literary", "scientific"], 1970),
    T("blacksite", "a facility that is not on any list", ["threatening", "cyberpunk"], 1990, weight=1.2),
    T("megablock", "housing stacked past the point of individual meaning", ["cyberpunk", "mundane"], 1975),
    T("greyzone", "the territory where jurisdiction is unclear", ["cyberpunk", "abstract"], 1985, weight=1.2),
    T("orbital", "a thing that keeps falling and keeps missing", ["scientific", "literary"], 1970),
    T("gantry", "the scaffold that holds something up before it leaves", ["literary", "mundane"], 1970),
    T("vatgrown", "manufactured biology; an insult with a technical basis", ["cyberpunk", "organic"], 1980, weight=1.1),
    T("nulldrift", "loss of position with nothing to correct against", ["abstract", "scientific"], 1980, register="insider"),
    T("cryowake", "the bad hour after the long sleep", ["literary", "gothic"], 1975, register="insider"),
    T("faraday", "the cage that keeps signals out or in", ["scientific", "cryptographic"], 1970, weight=1.3),
    T("deadzone", "where nothing reaches you, for better or worse", ["cyberpunk", "abstract"], 1980),
    T("hardlight", "the imaginary technology everyone borrowed", ["cyberpunk"], 1985, weight=0.8, register="pop"),
    T("longhaul", "the trip nobody volunteers for twice", ["mundane", "literary"], 1970),
    T("dustline", "the boundary weather draws across a place", ["literary", "gothic"], 1970, weight=1.1),
]

# ---------------------------------------------------------------------------
# CYBERPUNK — the texture of the scene itself.
# ---------------------------------------------------------------------------
CYBERPUNK = [
    T("chrome", "surface glamour bolted onto something older", ["cyberpunk"], 1984, weight=0.9, register="pop"),
    T("neon", "the light that makes any street look like a genre", ["cyberpunk"], 1982, weight=0.8, register="pop"),
    T("grid", "the infrastructure everyone depends on and nobody sees", ["cyberpunk", "network"], 1980, weight=1.2),
    T("mesh", "a network with no centre to seize", ["cyberpunk", "network"], 1995, weight=1.2),
    T("relay", "a point that passes things along without reading them", ["cyberpunk", "network"], 1975, weight=1.2),
    T("node", "one of many, deliberately", ["cyberpunk", "network", "minimal"], 1975),
    T("proxy", "someone standing where you would otherwise be", ["cyberpunk", "network"], 1990, weight=1.3),
    T("exitnode", "the last hop, where anonymity ends", ["cyberpunk", "network", "cryptographic"], 1998, weight=1.2, register="insider"),
    T("deadrop", "a message left in a place instead of sent", ["cyberpunk", "threatening"], 1975, weight=1.3),
    T("cutout", "an intermediary who does not know both ends", ["cyberpunk", "threatening"], 1970, weight=1.2, register="insider"),
    T("burner", "a thing designed to be discarded", ["cyberpunk", "mundane"], 1995, weight=1.2),
    T("skimmer", "a device that reads what was not offered", ["cyberpunk", "threatening"], 1990),
    T("blackout", "the interval with no record", ["cyberpunk", "abstract"], 1970, weight=1.1),
    T("streetlevel", "where the technology actually gets used", ["cyberpunk", "mundane"], 1984, weight=1.1),
    T("offbook", "unrecorded, unauthorised, deniable", ["cyberpunk", "threatening"], 1980, weight=1.2),
    T("greymarket", "legal enough to argue about", ["cyberpunk", "bureaucratic"], 1980),
    T("scrapyard", "where the previous generation went", ["cyberpunk", "mundane", "organic"], 1970),
    T("wiretap", "listening, made into a noun", ["cyberpunk", "surveillance", "threatening"], 1970, weight=1.2),
]

# ---------------------------------------------------------------------------
# PHREAK — telephone-era underground. Strongly period-marked on purpose.
# ---------------------------------------------------------------------------
PHREAK = [
    T("bluebox", "the tone generator that made long distance free", ["oldschool", "technical", "phreak"], 1971, 1995, weight=1.3, register="insider"),
    T("redbox", "the one that imitated coins dropping", ["oldschool", "technical", "phreak"], 1975, 1998, register="insider"),
    T("trunkline", "the shared circuit between exchanges", ["oldschool", "technical"], 1970, 2005),
    T("switchman", "the person who used to connect you by hand", ["oldschool", "mundane"], 1970, 2000, weight=1.2),
    T("dialtone", "the sound of a system waiting for instructions", ["oldschool", "minimal"], 1970, 2005, weight=1.3),
    T("busysignal", "refusal, rendered as a tone", ["oldschool", "irreverent"], 1970, 2005, weight=1.1),
    T("payphone", "infrastructure that took cash and asked nothing", ["oldschool", "mundane"], 1970, 2008, weight=1.2),
    T("partyline", "a circuit where everyone could hear everyone", ["oldschool", "network"], 1970, 2000),
    T("acoustic", "the coupler you pressed a handset into", ["oldschool", "technical"], 1970, 1995, register="insider"),
    T("carrier", "the tone that meant the other machine answered", ["oldschool", "technical"], 1975, 2005, weight=1.3),
    T("handshake", "two machines agreeing how to disagree", ["oldschool", "technical", "network"], 1975, weight=1.2),
    T("baudrate", "how fast the old world could speak", ["oldschool", "technical"], 1975, 2000, register="insider"),
    T("nodelist", "the directory of everyone worth calling", ["oldschool", "network", "bureaucratic"], 1984, 1998, register="insider"),
    T("sysop", "whoever owned the machine and therefore the rules", ["oldschool", "bureaucratic"], 1978, 2000, weight=1.3, register="insider"),
    T("ansiart", "pictures drawn from text characters", ["oldschool", "irreverent"], 1985, 2000, register="insider"),
    T("warez", "software liberated from its price", ["oldschool", "irreverent"], 1980, 2010, weight=1.1),
    T("courier", "the one who moved files before anyone else had them", ["oldschool", "mundane"], 1985, 2005, weight=1.2),
    T("scenewhore", "someone in it for the reputation, said with contempt", ["oldschool", "irreverent"], 1990, 2008, weight=0.7, register="insider"),
    T("greetz", "credits to friends, deliberately misspelled", ["oldschool", "irreverent"], 1988, 2005, weight=1.1, register="insider"),
    T("lamer", "the period-accurate insult", ["oldschool", "irreverent"], 1985, 2005, weight=0.8),
]

# ---------------------------------------------------------------------------
# MUNDANE — the mask. Boring on purpose.
# ---------------------------------------------------------------------------
MUNDANE = [
    T("accountant", "someone who knows exactly where everything went", ["mundane", "irreverent"], 1970, weight=1.2),
    T("gardener", "someone who prunes things quietly", ["mundane", "organic"], 1970, weight=1.2),
    T("plumber", "someone who deals with what flows underneath", ["mundane", "irreverent"], 1970, weight=1.3),
    T("milkman", "a job that stopped existing while nobody noticed", ["mundane", "oldschool"], 1970, weight=1.2),
    T("janitor", "the one with keys to every room", ["mundane", "irreverent"], 1970, weight=1.4),
    T("librarian", "the one who knows where everything is filed", ["mundane", "literary"], 1970, weight=1.3),
    T("locksmith", "a legitimate profession with an interesting skill set", ["mundane", "irreverent"], 1970, weight=1.3),
    T("postman", "delivery, unquestioned", ["mundane", "network"], 1970, weight=1.2),
    T("butcher", "precise work with unsettling vocabulary", ["mundane", "threatening"], 1970, weight=1.2),
    T("dentist", "unhurried proximity to pain", ["mundane", "threatening", "irreverent"], 1970, weight=1.1),
    T("nightporter", "whoever is awake at the desk at four", ["mundane", "gothic"], 1970, weight=1.2),
    T("meterman", "someone with a reason to be in your garden", ["mundane", "surveillance"], 1970, weight=1.2),
    T("baker", "up before everyone, gone before they arrive", ["mundane"], 1970),
    T("cobbler", "a trade name that outlived the trade", ["mundane", "oldschool"], 1970),
    T("ferryman", "paid to take you across and not to ask", ["mundane", "mythological"], 1970, weight=1.2),
    T("bookbinder", "someone who assembles what other people wrote", ["mundane", "literary"], 1970, weight=1.1),
    T("laundry", "where things are cleaned; also where money is", ["mundane", "irreverent"], 1970, weight=1.2),
    T("teakettle", "aggressively unthreatening", ["mundane", "irreverent"], 1970, weight=1.1),
    T("linoleum", "the least romantic surface available", ["mundane", "irreverent"], 1970, weight=1.2),
    T("thermostat", "quiet control over everyone's comfort", ["mundane", "irreverent"], 1970, weight=1.2),
    T("stapler", "so banal it becomes a statement", ["mundane", "irreverent", "minimal"], 1970, weight=1.1),
    T("tuesday", "the least eventful day, claimed as a name", ["mundane", "irreverent", "minimal"], 1970, weight=1.2),
    T("laundromat", "a public room where people wait", ["mundane", "irreverent"], 1970),
    T("porchlight", "left on for someone who may not come", ["mundane", "literary"], 1970, weight=1.1),
]

# ---------------------------------------------------------------------------
# BUREAUCRATIC — the language of institutions, used against them.
# ---------------------------------------------------------------------------
BUREAUCRATIC = [
    T("addendum", "the part added after everyone stopped reading", ["bureaucratic", "irreverent"], 1970, weight=1.2),
    T("subclause", "where the actual terms live", ["bureaucratic", "irreverent"], 1970, weight=1.2),
    T("redacted", "present, unreadable, and obviously important", ["bureaucratic", "cryptographic"], 1975, weight=1.3),
    T("footnote", "the small print that turns out to matter", ["bureaucratic", "literary"], 1970, weight=1.2),
    T("errata", "the official list of what was wrong", ["bureaucratic", "literary"], 1970),
    T("archivist", "whoever decides what is kept", ["bureaucratic", "literary"], 1970, weight=1.3),
    T("registry", "the list that makes a thing official", ["bureaucratic", "technical"], 1970),
    T("nihilobstat", "the stamp meaning nothing objectionable was found", ["bureaucratic", "literary"], 1970, weight=0.8, register="insider"),
    T("proforma", "done for the form of it, not the substance", ["bureaucratic", "irreverent"], 1970, weight=1.1),
    T("sundry", "the category for everything that fits nowhere", ["bureaucratic", "minimal"], 1970, weight=1.2),
    T("quorum", "the minimum number of people required to decide", ["bureaucratic", "minimal"], 1970, weight=1.1),
    T("intransit", "officially between two places and therefore nowhere", ["bureaucratic", "abstract"], 1970, weight=1.2),
    T("pending", "the status that never resolves", ["bureaucratic", "abstract", "minimal"], 1970, weight=1.2),
    T("nofault", "the finding that assigns blame to no one", ["bureaucratic", "irreverent"], 1970),
    T("caseworker", "the person assigned to your file", ["bureaucratic", "mundane"], 1970, weight=1.1),
]

# ---------------------------------------------------------------------------
# ORGANIC — damp, biological, decaying. The "mildew" register.
# ---------------------------------------------------------------------------
ORGANIC = [
    T("mildew", "quiet damage in a place nobody airs out", ["organic", "irreverent"], 1970, weight=1.4),
    T("lichen", "two organisms pretending to be one", ["organic", "scientific"], 1970, weight=1.3),
    T("spore", "small, patient, and everywhere already", ["organic", "threatening", "minimal"], 1970, weight=1.3),
    T("mycelium", "the network under everything, doing the actual work", ["organic", "network"], 1970, weight=1.3),
    T("compost", "controlled rot that produces something useful", ["organic", "irreverent"], 1970, weight=1.2),
    T("rustbelt", "corrosion as an economic region", ["organic", "mundane"], 1980, weight=1.1),
    T("moss", "slow, soft, and eventually structural", ["organic", "minimal"], 1970, weight=1.2),
    T("bracken", "the undergrowth you cannot walk through", ["organic", "gothic"], 1970),
    T("marrow", "the living part inside the structural part", ["organic", "gothic"], 1970, weight=1.2),
    T("tinder", "dry material waiting for one spark", ["organic", "threatening"], 1970, weight=1.2),
    T("bloom", "sudden overwhelming growth; usually algae, usually bad", ["organic", "scientific"], 1970, weight=1.2),
    T("hivemind", "coordination without a coordinator", ["organic", "network", "cyberpunk"], 1980, weight=0.9),
    T("driftwood", "carried a long way and worn smooth", ["organic", "literary"], 1970, weight=1.1),
    T("silt", "what settles when the current stops", ["organic", "abstract", "minimal"], 1970, weight=1.2),
    T("cicada", "seventeen years underground, then all at once", ["organic", "literary"], 1970, weight=1.3),
    T("nettle", "harmless-looking and not", ["organic", "threatening"], 1970, weight=1.2),
    T("fallow", "deliberately unused, for now", ["organic", "abstract", "minimal"], 1970, weight=1.2),
    T("weevil", "small, unwelcome, and already inside", ["organic", "threatening", "irreverent"], 1970, weight=1.2),
    T("brackish", "neither one thing nor the other", ["organic", "abstract"], 1970, weight=1.1),
    T("carrion", "what the scavengers are for", ["organic", "gothic", "threatening"], 1970),
]

# ---------------------------------------------------------------------------
# THREATENING — used sparingly; the system down-weights this on purpose.
# ---------------------------------------------------------------------------
THREATENING = [
    T("razor", "minimal and unambiguous", ["threatening", "minimal"], 1970, weight=1.1),
    T("venom", "delivered, not thrown", ["threatening"], 1970, weight=0.8),
    T("grave", "both a noun and an adjective", ["threatening", "gothic"], 1970),
    T("frost", "damage that looks like decoration", ["threatening", "gothic"], 1970, weight=1.1),
    T("scar", "evidence of something already survived", ["threatening", "gothic"], 1970, weight=1.1),
    T("wraith", "a threat with no body to fight", ["threatening", "gothic"], 1970, weight=0.8),
    T("reaper", "over-used but structurally sound", ["threatening", "gothic"], 1970, weight=0.6),
    T("ashfall", "the aftermath, drifting down", ["threatening", "gothic", "organic"], 1970, weight=1.2),
    T("blade", "simple, physical, and dated", ["threatening", "minimal"], 1970, weight=0.8),
    T("thorn", "defensive rather than aggressive", ["threatening", "organic", "minimal"], 1970, weight=1.2),
    T("viper", "patient and territorial", ["threatening", "organic"], 1970, weight=0.9),
    T("bruise", "the aftermath rather than the act", ["threatening", "organic", "irreverent"], 1970, weight=1.3),
    T("gallows", "the joke you make when it is too late", ["threatening", "gothic", "irreverent"], 1970, weight=1.2),
    T("tourniquet", "harm applied to prevent worse harm", ["threatening", "organic"], 1970, weight=1.2),
    T("quarantine", "isolation imposed for everyone else's sake", ["threatening", "bureaucratic"], 1970, weight=1.2),
    T("blacklist", "the list you cannot appeal", ["threatening", "bureaucratic"], 1970, weight=1.1),
]

POOLS = {
    "technical_terms": TECHNICAL,
    "crypto_terms": CRYPTO,
    "abstract_terms": ABSTRACT,
    "mythology": MYTH,
    "scifi": SCIFI,
    "cyberpunk": CYBERPUNK,
    "phreak_terms": PHREAK,
    "mundane": MUNDANE,
    "bureaucratic_terms": BUREAUCRATIC,
    "organic_terms": ORGANIC,
    "threatening": THREATENING,
}

SYSTEM = {
    "id": "underground-hacker-handle",
    "schema_version": 2,
    "description": (
        "Fictional Internet aliases inspired by BBS, IRC, warez, phreak, cypherpunk and "
        "underground computing cultures. Every term carries a gloss, semantic tags and a "
        "plausible period range, so the scorer can explain *why* a handle fits a character "
        "rather than just ranking it. The system deliberately favours specificity, wordplay "
        "and understatement over generic cyber-warrior branding."
    ),
    "archetypes": {
        "technical": {"enabled": True},
        "abstract": {"enabled": True},
        "mythological": {"enabled": True},
        "scifi": {"enabled": True},
        "mundane": {"enabled": True},
        "threatening": {"enabled": True},
        "minimal": {"enabled": True},
        "compound": {"enabled": True},
        "technical_myth": {"enabled": True},
        "mundane_threat": {"enabled": True},
        "ironic": {"enabled": True},
        "orthographic": {"enabled": True},
        "leet": {"enabled": True},
        "numeric": {"enabled": True},
        "prefix": {"enabled": True},
        "suffix": {"enabled": True},
        "acronym": {"enabled": True},
        "phonetic": {"enabled": True},
        "seeded": {"enabled": True},
    },
    **POOLS,
    "prefixes": ["null", "0x", "dead", "un", "sub", "anti", "para", "post", "counter", "de", "non"],
    "suffixes": ["null", "void", "x", "404", "13", "exe", "bin", "sys", "net", "org", "ish", "wise", "less", "core"],
    "separators": ["", "_", "-", "."],
    "digits": ["0", "1", "3", "7", "13", "17", "23", "42", "64", "88", "101", "127", "404", "451", "512", "1024"],
    "allowed_chars": "abcdefghijklmnopqrstuvwxyz0123456789_-",
    "max_length": 18,
    "min_length": 3,
    "preferred_lengths": [4, 5, 6, 7, 8, 9, 10, 11, 12],
    "transformations": ["leet", "drop-vowels", "truncate", "corrupt", "numeric", "phonetic", "separator"],
    "forbidden": [
        "hacker", "hackers", "cyberwarrior", "hackmaster", "elitehacker",
        "anonymous", "darkweb", "darknet", "ransomware", "terrorist",
    ],
    "overused": [
        "shadow", "dark", "cyber", "hack", "killer", "elite", "warrior",
        "ghost", "phantom", "ninja", "1337", "xx", "matrix", "neo",
    ],
    "generic_branding": [
        "hacker", "cyber", "cyberwarrior", "hackmaster", "elitehacker",
        "anonymous", "darkweb", "cybersecurity", "elitecoder",
    ],
    "archetype_weights": {
        "technical": 1.3, "abstract": 1.2, "compound": 1.4, "ironic": 1.2,
        "orthographic": 1.0, "minimal": 1.1, "mythological": 0.8, "scifi": 0.7,
        "mundane": 1.0, "threatening": 0.5, "technical_myth": 0.9,
        "mundane_threat": 0.8, "leet": 0.5, "numeric": 0.7, "prefix": 0.6,
        "suffix": 0.6, "acronym": 0.6, "phonetic": 0.8, "seeded": 1.5,
    },
    "score_weights": {},
}


def write(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", p)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    write(root / "profiles/underground-hacker-handle.json", SYSTEM)
    total = sum(len(v) for v in POOLS.values())
    print(f"{total} terms across {len(POOLS)} pools")
