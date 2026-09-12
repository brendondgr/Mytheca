"""The Embergate reference corpus — the durable lore the retrieval gate reaches for.

``retrieval_gate`` fires when a player names something off the present roster or asks a
who/what/when question about world history, and then ``rag/retriever`` searches this
corpus. On a fresh install there was nothing to find: the gate would open and the search
would come back empty, which reads on screen exactly like a gate that never opened.

So the seeded world ships the eight documents its own graph refers to. They are the
same facts the ``Faction``, ``Secret`` and ``Event`` nodes in ``core/seed_graph`` encode,
written out at the length a character would actually need to speak from — the graph says
*that* the Salt Writ happened and who it touched, and these say what it was like.

Rows only. Embedding is a separate, explicit step (``POST /storylines/{id}/rag/reindex/
stream``, or the Documents page's re-index action) because it downloads a model and takes
minutes; making startup wait on that would be a bad trade for an advisory feature.
"""

from __future__ import annotations

DOCUMENTS: list[dict] = [
    {
        "name": "the-drowned-court.md",
        "content": """# The Drowned Court

The Court is not a court and does not sit above the waterline. The name is a joke that
stopped being one about forty years ago, when the lower vaults flooded for good and the
people who had been running contraband through them simply stayed.

It has no charter, no roster anyone has seen, and no building it admits to. What it has
is the debt. Roughly two thirds of the lower town owes the Court money, a favour, or
silence, and it collects all three in the same tone of voice. A Court debt is never
called in at a convenient moment; that is the point of it.

**How it moves salt.** Sorcerer's salt comes in under legitimate cargo, in barrels that
are weighed at the customs house and weighed again, differently, at the Drowned Market.
The gap between the two weights is the trade. Everyone who signs either weight knows
there are two, which is why the Court has never needed to threaten a clerk.

**Who fronts it.** Publicly, nobody. In practice the Salt Guild's harbor factor — Maerin
Voss these last six years — negotiates on the Court's behalf while appearing to negotiate
against it. She has never been seen below the tideline and never had to be.

**What it fears.** Not the Tidewatch. The Court fears a written record, which is why the
loss of the harbor ledger was treated as a mercy by people who lost a great deal in the
same fire.
""",
    },
    {
        "name": "the-tidewatch-and-the-salt-writ.md",
        "content": """# The Tidewatch, and the Salt Writ that hollowed it

The Tidewatch is the harbor's law: eighty-odd men and women quartered in Tidewatch Keep,
answerable in theory to the upper town and in practice to whoever has most recently paid
their winter coal.

**The Salt Writ.** Nineteen years ago the Salt Guild bought the right to set the salt-tax
outright — not to collect it, which the Watch still does, but to *set* it. The writ was
legal, public, and the single most damaging thing to happen to Embergate in living memory.
It meant the Guild could price a rival out of the harbor by moving a number, and it meant
the Watch spent the next two decades enforcing a tax it had no hand in writing.

Since the writ, law in Embergate has been a line of credit. A watchman who arrests the
wrong debtor finds his own arrears reassessed within the month. Most stop making the
mistake. Captain Doran Hale has not, which is why he is a captain at forty-one and will
not be anything else.

**The failed raid.** Hale took twelve watchmen below the tideline eighteen months ago on
a tip he considered sound. The vaults were empty, swept, and the brazier in the
ledger-keeper's cage was still warm. He filed the report naming no one. The Watch has not
mounted an operation below the line since, and Hale has not stopped rereading his own
duty roster for that night.
""",
    },
    {
        "name": "the-chapel-fire.md",
        "content": """# The Chapel Fire

Two winters ago, fire took the upper nave of the Chapel of the Drowned. It began after
midnight, in the vestry, and it was seen from the harbor before anyone inside the building
knew about it.

Eleven people died. All eleven were in the undercroft, and all eleven died because the
tide had already sealed the stair — which it does, twice a day, on a schedule painted on
the wall beside it. The chapel had held the winter vigil in the undercroft for as long as
anyone could remember. It has not held one since.

**What was said afterwards.** That a lamp was left burning. That the roof timbers were
salt-rotted and would have gone anyway. That the vigil should never have been kept below
the tideline in the first place, which is true and which nobody said out loud until the
twelfth day.

**What was not said.** That the vestry had no lamp in it that night. Brother Aldous was
the one who found the stair sealed, and the one who has told the story most often, and
the one whose account has never once varied — which the Oracle of Salt has remarked on
twice, both times to no one in particular.

The eleven names are cut into the lintel. There is room for more, which was not an
accident of the mason's either.
""",
    },
    {
        "name": "the-drowned-ledger.md",
        "content": """# The drowned ledger

Embergate's master ledger recorded every licensed salt transaction in the harbor: buyer,
weight, duty paid, and the factor who signed for it. It was kept at the customs house,
audited twice yearly, and it went into the water the same night the chapel burned.

The official account is that a clerk carrying it to the Keep for safekeeping lost his
footing on the sea wall. The clerk in question left Embergate the following spring with
more money than he had earned.

**Why it matters.** The ledger names every salt buyer in the upper town. Not the
smugglers — the *customers*. Half the families who fund the Watch, endow the chapel, and
sit on the Guild's own board bought sorcerer's salt through licensed channels at prices
the writ made possible, and the ledger is the only place all of that was written down at
once.

**Where it is.** Nobody agrees. The Court behaves as though it has it. The Oracle behaves
as though it does not matter where it is. Wren Calloway was on the quay that night, says
she saw nothing, and has twice described the exact spot on the sea wall without being
asked.

A book that has been in salt water for two winters is not a book any more. This has not
stopped anyone looking for it.
""",
    },
    {
        "name": "the-tides-and-the-drowned-market.md",
        "content": """# The tides, and the market under them

Embergate's lower town floods twice a day. This is not a disaster; it is the timetable.
The bells in Tidewatch Keep count the turn, everyone below the third street plans around
them, and a stranger who does not know the bells is visible from a distance.

**The Drowned Market** trades in the window between. The vault rows are old warehouse
undercrofts, connected by plank walkways above the waterline, and they are dry for
somewhat under five hours at a stretch. Nothing traded there is illegal, because the
market is not there long enough to be anywhere.

Practical facts a local would know without thinking:

- The drowned stair from the harbor is passable at low tide only. At any other hour you
  go the long way, through the chapel undercroft, and you ask first.
- The tide-wardens at the arches are not guards. They are timekeepers, and they are the
  only people in the market everyone obeys.
- The lowest stalls are ankle-deep an hour before the bells. Sellers who are still there
  are either new or making a point.
- A boat inside the vault rows means someone expects to leave in a hurry.

**Why it cannot be raided.** Not because it is defended. Because the evidence walks out on
its own schedule, and a watch patrol that goes in late does not come out.
""",
    },
    {
        "name": "the-oracle-of-salt.md",
        "content": """# The Oracle of Salt

Nyssa reads the tide-basin in the sanctum behind the burnt nave. She has done so for
longer than anyone living can account for, and nobody remembers her arriving, which in a
town of eleven thousand people is itself the strangest fact about her.

**What she actually does.** She reads salt. A basin of seawater is left to stand and the
rings it leaves are read as they dry. Sailors pay for a reading before a voyage. Roughly
half sail against her counsel, and a fair number of those drown, which is generally taken
as proof she was right rather than as an argument about what she does.

**The third vision.** Eight months ago she read the basin, stopped mid-sentence, and did
not finish. She has not said aloud what she saw. She has since stopped taking payment
from sailors, which the chapel finds more alarming than the silence.

**Her standing.** The chapel keeps her and is afraid of her; the Guild has never once
tried to buy her; the Court leaves her entirely alone, which is not the Court's habit.
She speaks slowly and in tides, which people mistake for evasion. It is not. She is
describing something that arrives in layers.

She was the one who warned the chapel, the week before the fire, that the vigil should
not be held below the line.
""",
    },
    {
        "name": "salt-and-what-it-is-for.md",
        "content": """# Sorcerer's salt

There is no open magic in Embergate. There is salt, and there are people who pay a great
deal for a particular grade of it, and the town has long since stopped asking why.

**What it is.** Sea salt drawn from the drowned undercrofts rather than from a pan —
brine that has stood in the dark against old stone for a season or more. It is grey,
coarse, and faintly warm to the hand, which is the only property anyone can demonstrate
on request.

**What it is used for.** Preservation, in the ordinary trade. Warding, in the trade that
pays. Old bargains, in the trade nobody will name. The chapel uses it in the salt-circles
and will not discuss the practice with outsiders.

**Why it is controlled.** Not for danger — for price. Ordinary salt is a commodity. This
is not, it cannot be made faster than the tide makes it, and every undercroft that
produces it is under the waterline and therefore under the Court. The Salt Writ let the
Guild set a duty on it high enough that legitimate purchase became an upper-town luxury
and everything else became smuggling.

**The omens.** Salt left standing dries in rings, and the rings are read. This is the
whole of Embergate's supernatural life as far as any outsider can prove, and the locals
would like that kept in perspective.
""",
    },
    {
        "name": "who-owes-whom.md",
        "content": """# Who owes whom

A short, disputed, and locally indispensable summary. Anyone in the Saltworn could recite
most of it.

**The Salt Guild** licenses the trade and sets the tax. It is allied with the Drowned
Court for exactly as long as the writ holds, and not one season longer. It controls the
customs house in everything but the sign on the door.

**The Drowned Court** runs the lanes and holds the debt. It is at war with the Tidewatch
in the way weather is at war with a roof — continuously, without declaration, and with
only one plausible outcome. It has an arrangement with the chapel that predates everyone
currently party to it.

**The Tidewatch** holds the Keep and claims the customs house on paper. It is
underfunded by a Guild it is obliged to collect for, and it is the last body in Embergate
that still writes things down honestly, which is why both other powers treat its
paperwork as the real threat.

**The Chapel of the Drowned** holds the sanctum and what is left of the nave. Its
undercroft shares a wall with the market's vault rows, and always has. It is owed
something by the Court that the Court has never been asked to pay.

**Everyone else** owes one of the four. The ones who claim otherwise owe two.
""",
    },
]
